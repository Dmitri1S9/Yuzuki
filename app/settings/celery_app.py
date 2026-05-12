import os
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "archangel",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery.conf.update(
    imports=("app.tasks",),
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Vienna",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
