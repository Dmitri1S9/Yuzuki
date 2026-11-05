"""main.py — stage 3 (relations), read top to bottom and nowhere else. 3
named chapters, no logic of its own — pipeline.py says what each chapter
consists of, and steps/ (constants.py, character_relations.py,
group_relations.py, merge.py, low_info.py, io.py, persistence.py) says
how. See ARCHITECTURE.md.
"""
import os

# Must run before the import below — see cast/main.py's identical comment.
os.environ.setdefault("REDIS_URL_CACHE", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_URL_CELERY", "redis://localhost:6379/0")

from src.services.collection.relations.pipeline import collect_relations, merge_and_analyze, persist_and_publish
from src.services.collection.relations.steps.character_relations import create_client
from src.services.collection.relations.steps.io import configure_logging


def main():
    configure_logging()
    client = create_client()

    collection = collect_relations(client)
    collection = merge_and_analyze(collection)
    collection = persist_and_publish(collection)

    return collection.output


if __name__ == "__main__":
    main()
