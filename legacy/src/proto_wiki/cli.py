"""Entry point: python -m proto_wiki.cli --input <dump> --character "Kyoka Jiro" --out <dir>
(run from src/, or with PYTHONPATH=src). Only argparse and the __main__
boundary live here — everything else is main.run()'s conductor ladder."""
import argparse
import logging
import sys
from pathlib import Path

from . import main as main_module
from .errors import LoaderError
from .infra.ollama_client import LLMError, OllamaClient

log = logging.getLogger("proto_wiki")

DEFAULT_PARAMS = Path(__file__).resolve().parents[1] / "domain" / "parameters.json"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="proto_wiki", description="Граф и параметры персонажа по тексту вики (Ollama).")
    ap.add_argument("--input", required=True, help="дамп *_pages_current.xml, wikitext, plain text или папка с ними")
    ap.add_argument("--character", required=True, help='имя персонажа, например "Kyoka Jiro"')
    ap.add_argument("--params", default=str(DEFAULT_PARAMS), help="parameters.json (по умолчанию src/domain/parameters.json)")
    ap.add_argument("--out", required=True, help="папка для результатов и кеша")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--ctx", type=int, default=32768)
    ap.add_argument("--fresh", action="store_true", help="игнорировать кеш и пересчитать всё")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None, llm: OllamaClient | None = None) -> int:
    """`llm` is injectable so tests can run the whole pipeline on a mock."""
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if llm is None:
        llm = OllamaClient(args.model, ctx=args.ctx)
        llm.ensure_loaded()

    try:
        main_module.run(
            input_path=args.input, character=args.character, params_path=args.params,
            out_dir=Path(args.out), llm=llm, fresh=args.fresh,
        )
        # The error count is in report.md's own ERRORS section — the exit
        # code only distinguishes "ran to completion" from "couldn't even
        # start" (a LoaderError/LLMError below), same as before the reorg.
        return 0
    except (LoaderError, LLMError) as e:
        # The one deliberately inline log call in the whole prototype: the
        # __main__-boundary error-to-exit-code translation has nowhere else
        # to live — every entry point needs some place that isn't decorated.
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
