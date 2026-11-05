"""Словарь имён вселенной: кодом находит упоминания в абзаце и размечает их.

Это ядро "конструктивного" решения проблемы посторонних имён: модель никогда не пишет имя сама,
она выбирает из списка кандидатов, который построил этот код (см. methods/rel_anchored.py).

Алиасы: явные (из YAML / редиректов вики, см. samples/build_roster.py) + автоматические однословные
(имя и фамилия), если токен однозначен в ростере. Неоднозначный токен ("Jiro" = Kyoka/Kyotoku/Mika)
отдаётся владельцу страницы, если владелец среди претендентов, иначе отбрасывается.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Entity:
    name: str
    kind: str  # "character" | "group"
    aliases: tuple[str, ...] = ()


@dataclass
class Roster:
    entities: list[Entity]
    owner: str | None = None
    _patterns: list[tuple[re.Pattern, str]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        surface: dict[str, set[str]] = {}
        for e in self.entities:
            for s in (e.name, *e.aliases):
                surface.setdefault(s, set()).add(e.name)
        explicit = set(surface)
        tokens: dict[str, set[str]] = {}
        for e in self.entities:
            if e.kind != "character":
                continue
            for tok in e.name.split():
                if len(tok) > 2 and tok[0].isupper() and tok not in explicit:
                    tokens.setdefault(tok, set()).add(e.name)
        for tok, names in tokens.items():
            if len(names) == 1:
                surface.setdefault(tok, set()).update(names)
            elif self.owner in names:
                surface.setdefault(tok, set()).add(self.owner)
        # explicit ambiguous surfaces: same rule
        resolved: dict[str, str] = {}
        for s, names in surface.items():
            if len(names) == 1:
                resolved[s] = next(iter(names))
            elif self.owner in names:
                resolved[s] = self.owner
        # longest first, so "Kyoka Jiro" wins over "Jiro"
        self._patterns = [
            (re.compile(r"(?<![\w-])" + re.escape(s) + r"(?:'s)?(?![\w-])"), n)
            for s, n in sorted(resolved.items(), key=lambda kv: -len(kv[0]))
        ]

    @classmethod
    def load(cls, path: Path, owner: str | None = None) -> "Roster":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        ents = [Entity(c["name"], "character", tuple(c.get("aliases") or ())) for c in data.get("characters", [])]
        ents += [Entity(g["name"], "group", tuple(g.get("aliases") or ())) for g in data.get("groups", [])]
        return cls(ents, owner)

    def kind(self, name: str) -> str | None:
        return next((e.kind for e in self.entities if e.name == name), None)

    def spans(self, text: str) -> list[tuple[int, int, str]]:
        """Непересекающиеся упоминания (start, end, canonical name), длинные приоритетнее."""
        taken = [False] * len(text)
        found = []
        for pat, name in self._patterns:
            for m in pat.finditer(text):
                if any(taken[m.start():m.end()]):
                    continue
                for i in range(m.start(), m.end()):
                    taken[i] = True
                found.append((m.start(), m.end(), name))
        return sorted(found)

    def mentions(self, text: str) -> list[str]:
        """Канонические имена, упомянутые в тексте, в порядке первого появления."""
        seen: list[str] = []
        for _, _, n in self.spans(text):
            if n not in seen:
                seen.append(n)
        return seen

    def resolve(self, surface: str) -> str | None:
        """Свободная строка от модели -> каноническое имя (точное совпадение с алиасом/именем)."""
        s = surface.strip()
        for pat, name in self._patterns:
            if pat.fullmatch(s) or pat.fullmatch(s.removesuffix("'s")):
                return name
        return None

    def mark(self, text: str) -> str:
        """Entity markers: "Denki" -> "[Denki](Denki Kaminari)". Модель видит каноническое имя рядом с упоминанием."""
        out, last = [], 0
        for s, e, n in self.spans(text):
            out.append(text[last:s])
            frag = text[s:e]
            out.append(f"[{frag}]" if frag == n else f"[{frag}]({n})")
            last = e
        out.append(text[last:])
        return "".join(out)
