"""main.py — stage 1 (cast + groups), read top to bottom and nowhere else.
4 named chapters, no logic of its own — pipeline.py says what each chapter
consists of, and steps/ (constants.py, roster.py, groups.py, images.py,
output.py, persistence.py) says how. See ARCHITECTURE.md.
"""
import os

# Must run before the import below, which pulls in the AI-client stack and
# instantiates Settings() at import time — a local (non-docker) run has no
# REDIS_URL_CACHE/REDIS_URL_CELERY env var otherwise. In docker these are
# already set by docker-compose.yaml and this is a no-op.
os.environ.setdefault("REDIS_URL_CACHE", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_URL_CELERY", "redis://localhost:6379/0")

from src.services.collection.cast.pipeline import (
    assemble_and_publish, build_roster_and_groups, collect_candidates, reconcile_names,
)
from src.services.collection.cast.steps.groups import create_client
from src.services.collection.cast.steps.output import configure_logging


def main():
    configure_logging()
    client = create_client()

    collection = collect_candidates(client)
    collection = reconcile_names(collection)
    collection = build_roster_and_groups(collection)
    output = assemble_and_publish(collection)

    return output


if __name__ == "__main__":
    main()
