"""Yuzuki's API — exists for one reason: DCS calls it to confirm reviewed
data (see routes/confirm.py) and to browse universes (routes/universes.py).
Not a general-purpose API; there's no route for triggering pipeline stages
or anything else — those still run as separate `docker compose run`
invocations, same as always.
"""
from fastapi import FastAPI

from src.api.routes import confirm, universes

app = FastAPI(title="Yuzuki API")
app.include_router(universes.router)
app.include_router(confirm.router)


@app.get("/health")
def health():
    return {"status": "ok"}
