"""Jinja2 prompt rendering — the prototype's counterpart to
src/infra/prompts/loader.py in the main pipeline (not shared with it:
proto_wiki is its own standalone service, own template set)."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ..repository.step_cache import digest

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "prompts"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR), trim_blocks=True, lstrip_blocks=True, undefined=StrictUndefined,
)


def render(name: str, **kwargs) -> str:
    return _env.get_template(f"{name}.j2").render(**kwargs)


def templates_digest(*names: str) -> str:
    """Cache-key ingredient: a hash of the rendered templates' own source,
    so editing a .j2 file invalidates the cache on its own."""
    return digest([(TEMPLATES_DIR / f"{n}.j2").read_text(encoding="utf-8") for n in names])
