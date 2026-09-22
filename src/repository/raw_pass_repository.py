"""Cache of features stage's raw per-character/per-param Gemini scores —
replaces pass{N}_{SLUG}.csv. Purely a same-stage re-run cost cache (skip
re-paying for a collection pass on a debug rerun), not inter-stage handoff.
"""
import logging

from src.repository.connection import read_only, transactional

log = logging.getLogger(__name__)


class RawPassRepository:

    @read_only
    def get_passes(self, conn, universe_id: int, passes: tuple[int, ...]) -> dict[int, dict] | None:
        """None unless every requested pass has at least one saved row —
        same all-or-nothing semantics have_pass_csvs had for the CSV files."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT pass_number FROM raw_passes WHERE universe_id = %s AND pass_number = ANY(%s)",
                (universe_id, list(passes)),
            )
            present = {row[0] for row in cur.fetchall()}
        if present != set(passes):
            return None

        with conn.cursor() as cur:
            cur.execute(
                "SELECT pass_number, param, name, score FROM raw_passes "
                "WHERE universe_id = %s AND pass_number = ANY(%s)",
                (universe_id, list(passes)),
            )
            rows = cur.fetchall()
        per_pass: dict[int, dict] = {p: {} for p in passes}
        for pass_number, param, name, score in rows:
            per_pass[pass_number].setdefault(param, {})[name] = score
        return per_pass

    @transactional
    def save_pass(self, conn, universe_id: int, pass_number: int, scores_by_param: dict[str, dict]) -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM raw_passes WHERE universe_id = %s AND pass_number = %s",
                        (universe_id, pass_number))
            for param, scores in scores_by_param.items():
                for name, score in scores.items():
                    cur.execute(
                        "INSERT INTO raw_passes (universe_id, pass_number, param, name, score) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (universe_id, pass_number, param, name, score),
                    )
        log.info("saved pass %d raw scores for universe %d (%d param(s))",
                  pass_number, universe_id, len(scores_by_param))
