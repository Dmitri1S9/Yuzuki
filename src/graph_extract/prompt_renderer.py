import hashlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PACKAGE_DIR = Path(__file__).resolve().parent


class PromptRenderer:
    def __init__(self):
        self._env = Environment(loader=FileSystemLoader(PACKAGE_DIR / "prompts"), undefined=StrictUndefined,
                                keep_trailing_newline=True)

    def action(self, section: str, text: str, universe: str, characters, groups) -> str:
        return self._env.get_template("action_prompt.j2").render(
            section=section, text=text, universe=universe, characters=characters, groups=groups)

    def template_hash(self, template: str = "action_prompt.j2") -> str:
        source = self._env.loader.get_source(self._env, template)[0]
        return hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]
