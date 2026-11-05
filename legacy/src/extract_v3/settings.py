"""Config for extract_v3. Fully standalone -- no dependency on any earlier prototype."""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class RosterEntry:
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    universe: str
    target_character: str
    pages: tuple[str, ...]
    dump_path: Path
    drop_sections: tuple[str, ...]
    model: str
    temperature: float
    think: bool
    num_ctx: int
    num_predict: int
    keep_alive: str
    timeout_s: float
    retries: int
    embedding_model: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    characters: tuple[RosterEntry, ...]
    groups: tuple[RosterEntry, ...]

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Settings":
        raw = yaml.safe_load(Path(path or PACKAGE_DIR / "config.yaml").read_text(encoding="utf-8"))
        env = _prefixed_env("NEO4J_")
        return cls(
            universe=raw["universe"], target_character=raw["target_character"], pages=tuple(raw["pages"]),
            dump_path=Path(raw["dump_path"]).expanduser(),
            drop_sections=tuple(s.lower() for s in raw["drop_sections"]),
            model=raw["llm"]["model"], temperature=raw["llm"]["temperature"], think=raw["llm"]["think"],
            num_ctx=raw["llm"]["num_ctx"], num_predict=raw["llm"]["num_predict"],
            keep_alive=raw["llm"]["keep_alive"], timeout_s=raw["llm"]["timeout_s"], retries=raw["llm"]["retries"],
            embedding_model=raw["embedding"]["model"],
            neo4j_uri=env.get("NEO4J_URI", raw["neo4j"]["default_uri"]),
            neo4j_user=env.get("NEO4J_USER", raw["neo4j"]["default_user"]),
            neo4j_password=env.get("NEO4J_PASSWORD", ""),
            characters=tuple(RosterEntry(c["name"], tuple(c.get("aliases", []))) for c in raw["roster"]["characters"]),
            groups=tuple(RosterEntry(g["name"], tuple(g.get("aliases", []))) for g in raw["roster"]["groups"]),
        )


def _prefixed_env(prefix: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.startswith(prefix)}
    dotenv = PACKAGE_DIR.parent.parent / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip().startswith(prefix) and key.strip() not in env:
                env[key.strip()] = value.strip().strip("'\"")
    return env
