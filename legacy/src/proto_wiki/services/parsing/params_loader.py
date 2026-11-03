"""Reads parameters.json into a list of Param entities. Pure parsing logic,
no I/O beyond reading the given files."""
import json
import re
from collections import Counter
from pathlib import Path

from ...domain.param import Param
from ...errors import ParamsFormatError
from ...shared.decorators import logged

_DEFAULT_TIER_COUNT = 5
_TIER_LINE = re.compile(r"^\[(T\d+)\]\s+(.+?)\s*$", re.M)


@logged(lambda params, path: f"Параметры из {path}: флагов {sum(not p.ordinal for p in params)}, "
        f"ординалов {sum(p.ordinal for p in params)}")
def load_params(path: str | Path) -> list[Param]:
    """Structure (see src/domain/parameters.py in the main pipeline):
    top-level `ordinals` {name: {definition, tier_count, ...}}, `profile`
    (collected elsewhere, skipped here), and every other key is a category
    of flags {name: {definition, sort_axis}}. Anything else is an error —
    never silently treated as flags."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ParamsFormatError(f"Не удалось прочитать {path}: {e}") from e
    if not isinstance(raw, dict):
        raise ParamsFormatError(f"{path}: верхний уровень должен быть объектом, а не {type(raw).__name__}")
    ordinals_raw = raw.get("ordinals")
    if not isinstance(ordinals_raw, dict) or not ordinals_raw:
        raise ParamsFormatError(
            f"{path}: нет ключа `ordinals` с объектом ординалов (нашёл ключи: {list(raw)}) — структура не распознана"
        )

    templates_dir = path.parent.parent / "infra" / "prompts" / "templates"
    params: list[Param] = []

    for name, meta in ordinals_raw.items():
        if not isinstance(meta, dict) or not isinstance(meta.get("definition"), str):
            raise ParamsFormatError(f"{path}: ordinals.{name} должен быть объектом с полем `definition`")
        tiers = _ordinal_tiers(name, meta, path)
        params.append(Param(
            name=name, ordinal=True, definition=meta["definition"], tiers=tiers + ["unknown"],
            tier_descriptions=_tier_descriptions(templates_dir, meta.get("prompt_template"), tiers),
        ))

    flag_categories = 0
    for category, entries in raw.items():
        if category in ("ordinals", "profile"):
            continue
        if not isinstance(entries, dict):
            raise ParamsFormatError(f"{path}: категория `{category}` должна быть объектом флагов")
        flag_categories += 1
        for name, meta in entries.items():
            if not isinstance(meta, dict) or not isinstance(meta.get("definition"), str):
                raise ParamsFormatError(f"{path}: {category}.{name} должен быть объектом с полем `definition`")
            params.append(Param(
                name=name, ordinal=False, definition=meta["definition"],
                tiers=["T1", "T2", "T3", "unknown"], sort_axis=meta.get("sort_axis"),
            ))
    if flag_categories == 0:
        raise ParamsFormatError(f"{path}: не нашёл ни одной категории флагов (ключи: {list(raw)})")

    names = [p.name for p in params]
    dupes = [n for n, c in Counter(names).items() if c > 1]
    if dupes:
        raise ParamsFormatError(f"{path}: повторяющиеся имена параметров: {dupes}")
    return params


def _ordinal_tiers(name: str, meta: dict, path: Path) -> list[str]:
    if isinstance(meta.get("tiers"), list) and meta["tiers"]:
        return [str(t) for t in meta["tiers"]]
    count = meta.get("tier_count", _DEFAULT_TIER_COUNT)
    if not isinstance(count, int) or isinstance(count, bool) or count < 2:
        raise ParamsFormatError(f"{path}: ordinals.{name}.tier_count должен быть целым >= 2, а не {count!r}")
    return [f"T{i}" for i in range(1, count + 1)]


def _tier_descriptions(templates_dir: Path, template_name: str | None, tiers: list[str]) -> dict[str, str]:
    """Best effort: the repo's existing ordinal prompt templates carry the
    tier calibration as `[T3]  description` lines; reuse them if they are
    there, otherwise the scale stays undescribed (just T1 lowest..Tn top)."""
    if not template_name:
        return {}
    tpl = templates_dir / f"{template_name}.j2"
    if not tpl.is_file():
        return {}
    found = dict(_TIER_LINE.findall(tpl.read_text(encoding="utf-8")))
    return {t: found[t] for t in tiers if t in found}
