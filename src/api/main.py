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
from fastapi.responses import JSONResponse

from src.api.routes import confirm, features, library, media, pipeline, relations, universes
from src.infra.exceptions import CharacterException

app = FastAPI(title="Yuzuki API")
app.include_router(universes.router)
app.include_router(confirm.router)
app.include_router(features.router)
app.include_router(library.router)
app.include_router(relations.router)
app.include_router(pipeline.router)
app.include_router(media.router)


@app.exception_handler(CharacterException)
async def character_not_found_handler(request, exc: CharacterException):
    # Same detail text every route used to hand-roll via HTTPException(404,
    # ...) — kept identical so DCS's handling of this response doesn't change.
    return JSONResponse(status_code=404,
                         content={"detail": f"character {exc.name!r} not found in universe {exc.universe_id}"})


@app.get("/health")
def health():
    return {"status": "ok"}
