"""Where this run's ephemeral inter-stage handoff files live — see
ARCHITECTURE.md's "Inter-stage JSON files vs. the database" section. Kept in
one subdirectory instead of scattered loose across the project root.
"""
import os

RUN_DIR = "run"


def run_path(filename: str) -> str:
    os.makedirs(RUN_DIR, exist_ok=True)
    return os.path.join(RUN_DIR, filename)
