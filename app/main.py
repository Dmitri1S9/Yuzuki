import logging
from fastapi import FastAPI

log = logging.getLogger(__name__)

app = FastAPI(title="Yuzuki")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8044, reload=True)

