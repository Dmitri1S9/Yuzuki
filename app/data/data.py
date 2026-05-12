from pathlib import Path
from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
)

def get_prompt(template_name: str, **kwargs) -> str:
    template = _env.get_template(f"prompts_ordinal_v2/{template_name}.j2")
    return template.render(**kwargs)
