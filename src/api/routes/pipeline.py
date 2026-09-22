"""The one narrow exception to "no route triggers a pipeline stage" (see
api/main.py's docstring) — DCS calls this once a human has approved the
*task* of running the next stage (a separate approval from reviewing the
data itself, see api/routes/confirm.py). Enqueues a Celery task
(src/services/pipeline_tasks.py) and returns immediately; the actual stage
runs in celery_worker, not in this API process.
"""
from fastapi import APIRouter, HTTPException

from src.api.schemas import PipelineRunRequest
from src.services.pipeline_tasks import STAGE_MODULES, run_stage

router = APIRouter(tags=["pipeline"])


@router.post("/pipeline/{stage}/run")
def run_pipeline_stage(stage: str, body: PipelineRunRequest):
    if stage not in STAGE_MODULES:
        raise HTTPException(status_code=400, detail=f"unknown stage: {stage!r}, expected one of {sorted(STAGE_MODULES)}")
    task = run_stage.delay(stage, body.universe_id)
    return {"status": "queued", "task_id": task.id}
