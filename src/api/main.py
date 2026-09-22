"""Yuzuki's API — exists for one reason: DCS calls it to confirm reviewed
data (see routes/confirm.py) and to browse universes (routes/universes.py).
Not a general-purpose API. Two narrow exceptions to "no route triggers a
pipeline stage": routes/universes.py's refresh-image endpoint (re-runs
stage 1's image lookup for one already-known character on demand — a retry
of one field, not a stage), and routes/pipeline.py's run endpoint (enqueues
a Celery task that launches the *next* stage as its own fresh subprocess,
called only once a human has separately approved doing so in DCS — see
routes/pipeline.py and src/services/pipeline_tasks.py for why it's a
subprocess and not an in-process call).
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.routes import confirm, features, library, pipeline, relations, universes
from src.services.collection.cast.steps.images import MEDIA_DIR

app = FastAPI(title="Yuzuki API")
app.include_router(universes.router)
app.include_router(confirm.router)
app.include_router(features.router)
app.include_router(library.router)
app.include_router(relations.router)
app.include_router(pipeline.router)

MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/characters", StaticFiles(directory=MEDIA_DIR), name="media")


@app.get("/health")
def health():
    return {"status": "ok"}
