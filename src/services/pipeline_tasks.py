"""The one Celery task: launch a pipeline stage as a fresh subprocess for a
given, already-approved universe.

Why a subprocess and not a plain in-process function call: each stage's
constants.py (e.g. src/services/collection/relations/steps/constants.py)
reads sys.argv exactly once, at module import time
(UNIVERSE_NAME, ARC, ... = parse_universe_args(...)). A Celery worker is a
long-lived process — if this task imported relations.main and called it
directly, the constants module would only ever be imported (and its
sys.argv parsed) once, on the *first* task this worker ever handles; every
later task, for any other universe, would silently keep using that first
universe's frozen name/arc. A fresh subprocess gets a fresh interpreter and
correctly parses its own argv every time — the exact same command a human
typed by hand all session, just launched by a worker instead of a terminal.
"""
import logging
import subprocess

from src.infra.celery_app import app
from src.repository import UniverseRepository
from src.shared.decorators import logged

# The stdout/stderr dump below (on failure only) stays a plain inline log
# call, not a decorator — same carve-out as OllamaClient's own retry/VRAM
# diagnostics: it's raw output from an external subprocess at a failure
# boundary, needed right before raising, not narration of this task's own
# business logic.
log = logging.getLogger(__name__)
_universe_repo = UniverseRepository()

STAGE_MODULES = {
    "relations": "src.services.collection.relations.main",
    "features": "src.services.collection.features.main",
}


@logged(lambda _, stage, universe_id, universe_name, args:
        f"launching stage {stage!r} for universe {universe_id} ({universe_name!r}): {args}")
def _log_launching_stage(stage: str, universe_id: int, universe_name: str, args: list[str]) -> None:
    pass


@logged(lambda _, stage, universe_id, returncode: f"stage {stage!r} for universe {universe_id} finished with code {returncode}")
def _log_stage_finished(stage: str, universe_id: int, returncode: int) -> None:
    pass


@app.task(name="pipeline.run_stage")
def run_stage(stage: str, universe_id: int) -> dict:
    if stage not in STAGE_MODULES:
        raise ValueError(f"unknown stage: {stage!r}, expected one of {sorted(STAGE_MODULES)}")

    universe = _universe_repo.get_universe_by_id(universe_id)
    if universe is None:
        raise RuntimeError(f"universe {universe_id} not found")

    args = [
        "conda", "run", "--no-capture-output", "-n", "analyse_service",
        "python", "-m", STAGE_MODULES[stage],
        universe.get_name(), universe.get_arc() or "", "", universe.get_anilist_title(),
    ]
    _log_launching_stage(stage, universe_id, universe.get_name(), args)
    result = subprocess.run(args, cwd="/app", capture_output=True, text=True)
    _log_stage_finished(stage, universe_id, result.returncode)
    if result.returncode != 0:
        log.error("stage %r stdout:\n%s", stage, result.stdout[-4000:])
        log.error("stage %r stderr:\n%s", stage, result.stderr[-4000:])
        raise RuntimeError(f"stage {stage!r} for universe {universe_id} failed (exit {result.returncode})")
    return {"stage": stage, "universe_id": universe_id, "status": "completed"}
