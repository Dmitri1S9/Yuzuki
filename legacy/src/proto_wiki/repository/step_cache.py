"""StepCache — the disk-backed cache for steps 1-3's JSON output, the
prototype's analogue of a DB repository: callers ask for a step's result by
cache key and get it back or None, never touch the file format themselves.
"""
import hashlib
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def digest(*parts) -> str:
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class StepCache:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir

    def read(self, filename: str, key: str, fresh: bool) -> dict | None:
        path = self.out_dir / filename
        if fresh or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("%s повреждён — пересчитываю", filename)
            return None
        if data.get("cache_key") != key:
            log.info("%s устарел (изменились вход, модель или промпт) — пересчитываю", filename)
            return None
        return data

    def write(self, filename: str, data: dict) -> None:
        path = self.out_dir / filename
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
