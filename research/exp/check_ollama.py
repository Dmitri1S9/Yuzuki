"""Шаг 0: проверить, что ваша версия Ollama реально соблюдает enum в format при think=false.

    python -m research.exp.check_ollama --model qwen3.5:9b

Просим модель назвать имя, которого нет в enum. Если вернулось что-то вне списка — grammar не применяется
(известный баг ollama#14645 на части версий) и методы M1–M3 теряют гарантию; обновите Ollama.
"""
import argparse
import time

from .llm import OllamaLLM

ALLOWED = ["Denki Kaminari", "Momo Yaoyorozu"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:9b")
    args = ap.parse_args()
    llm = OllamaLLM(args.model)
    schema = {"type": "object", "properties": {"name": {"type": "string", "enum": ALLOWED}}, "required": ["name"]}
    bad = 0
    t0 = time.monotonic()
    for _ in range(3):
        ans = llm.chat("Answer with JSON.", "Who is the main villain of Star Wars? Answer 'Darth Vader'.", schema, 20)
        name = (ans or {}).get("name")
        print("->", name)
        bad += name not in ALLOWED
    dt = (time.monotonic() - t0) / 3
    print(f"\n{'OK: enum enforced' if not bad else 'FAIL: enum NOT enforced'}; {dt:.2f}s/call; "
          f"errors={llm.stats.errors}, schema_violations={llm.stats.schema_violations}")


if __name__ == "__main__":
    main()
