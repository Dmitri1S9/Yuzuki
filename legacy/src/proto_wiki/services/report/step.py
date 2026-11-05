"""Step 4: report.md. Errors get their own section and never appear in the
yes / no / don't-know lists."""
from ...domain.schemas import ParamResult


def _quote(r: ParamResult) -> str:
    return f"«{r.evidence}»" if r.evidence else "(без цитаты)"


def build_report(character: str, model: str, results: list[ParamResult], step_errors: list[str]) -> str:
    flags = [r for r in results if not r.ordinal]
    ordinals = [r for r in results if r.ordinal]
    yes = [r for r in flags if r.status == "ok" and r.tier == "T3"]
    no = [r for r in flags if r.status == "ok" and r.tier == "T1"]
    dont_know = [r for r in flags if r.status != "error" and r not in yes and r not in no]
    errors = [r for r in results if r.status == "error"]

    out = [f"# {character}: параметры по тексту вики", "", f"Модель: {model}. Флагов: {len(flags)}, ординалов: {len(ordinals)}.", ""]

    out += [f"## Флаги: да (T3) — {len(yes)}", ""]
    out += [f"- **{r.name}** — {_quote(r)}" for r in yes] or ["_нет_"]

    out += ["", f"## Флаги: нет (T1) — {len(no)}", ""]
    out += [f"- **{r.name}** — {_quote(r)}" for r in no] or ["_нет_"]

    out += ["", f"## Флаги: не знает — {len(dont_know)}", ""]
    for r in dont_know:
        if r.status == "evidence_not_found":
            out.append(f"- **{r.name}** [evidence_not_found: модель ответила {r.tier}, цитаты нет в тексте] — {_quote(r)}")
        elif r.tier == "T2":
            out.append(f"- **{r.name}** [T2: неясно] — {_quote(r)}")
        else:
            out.append(f"- **{r.name}** [unknown: текст молчит]")
    if not dont_know:
        out.append("_нет_")

    out += ["", "## Ординалы", ""]
    for r in ordinals:
        if r.status == "error":
            out.append(f"- **{r.name}** — см. ERRORS")
        elif r.status == "evidence_not_found":
            out.append(f"- **{r.name}** — не подтверждено [evidence_not_found: модель ответила {r.tier}] — {_quote(r)}")
        elif r.tier == "unknown":
            out.append(f"- **{r.name}** — unknown (текст молчит)")
        else:
            out.append(f"- **{r.name}** — **{r.tier}** — {_quote(r)}")
    if not ordinals:
        out.append("_нет_")

    out += ["", f"## ERRORS — {len(errors) + len(step_errors)}", ""]
    out += [f"- параметр **{r.name}**: {r.reason}" for r in errors]
    out += [f"- {e}" for e in step_errors]
    if not errors and not step_errors:
        out.append("_нет_")
    return "\n".join(out) + "\n"
