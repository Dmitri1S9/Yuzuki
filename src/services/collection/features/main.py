"""main.py — stage 2 (ordinal ranks + flags + profile), read top to bottom
and nowhere else. 3 named chapters, no logic of its own — pipeline.py says
what each chapter consists of, and steps/ (constants.py, collection.py,
merge.py, io.py, persistence.py) says how. See ARCHITECTURE.md.
"""
import os

# Must run before the import below — see cast/main.py's identical comment.
os.environ.setdefault("REDIS_URL_CACHE", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_URL_CELERY", "redis://localhost:6379/0")

from src.services.collection.features.pipeline import (
    assemble_and_publish, build_consensus_and_features, prepare_and_collect,
)
from src.services.collection.features.steps.collection import create_client
from src.services.collection.features.steps.io import configure_logging


def main():
    configure_logging()
    client = create_client()

    collection = prepare_and_collect(client)
    collection = build_consensus_and_features(client, collection)
    collection = assemble_and_publish(collection)

    return collection.output


if __name__ == "__main__":
    main()
