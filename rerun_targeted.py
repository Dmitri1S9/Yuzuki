"""
Targeted rerun: lawfulness (all arcs) + science + honest (all arcs).
Reads characters from the existing DB to avoid re-running create_universe.
"""
import json
from db.service import get_universe_characters, get_universe
from app.tasks import rank_task, flag_task

UNIVERSE_IDS = {
    "Year 1": 1,
    "Year 2": 2,
    "Year 3": 3,
}

UNIVERSE_NAME = "Classroom of the Elite"


def rerun_for_arc(arc: str, universe_id: int):
    chars_rows = get_universe_characters(universe_id)
    if not chars_rows:
        print(f"[{arc}] No characters found for universe_id={universe_id}, skipping")
        return
    characters = [r["name"] for r in chars_rows]
    print(f"[{arc}] universe_id={universe_id}, {len(characters)} chars")

    # lawfulness
    t = rank_task.delay(
        "user_prompt_lawfulness", characters,
        UNIVERSE_NAME, universe_id, "lawfulness", arc=arc
    )
    print(f"  [lawfulness] dispatched task {t.id}")

    # science flag
    t = flag_task.delay(
        "science", characters, UNIVERSE_NAME, universe_id, arc=arc
    )
    print(f"  [science]    dispatched task {t.id}")

    # honest flag
    t = flag_task.delay(
        "honest", characters, UNIVERSE_NAME, universe_id, arc=arc
    )
    print(f"  [honest]     dispatched task {t.id}")


if __name__ == "__main__":
    for arc, uid in UNIVERSE_IDS.items():
        rerun_for_arc(arc, uid)
    print("\nAll tasks dispatched. Watch celery_worker logs.")
