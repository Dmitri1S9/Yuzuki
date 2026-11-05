"""The Celery app instance — a queueing/dispatch layer around launching a
pipeline stage as its own fresh subprocess, see pipeline_tasks.py for why a
fresh process (not an in-worker function call) is required.
"""
from celery import Celery

from src.infra.settings.config import Settings

_settings = Settings()

app = Celery(
    "yuzuki", broker=_settings.redis_url_celery, backend=_settings.redis_url_celery,
    include=["src.services.pipeline_tasks"],
)
