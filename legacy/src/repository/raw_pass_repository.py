"""Cache of features stage's raw per-character/per-param Gemini scores —
replaces pass{N}_{SLUG}.csv. Purely a same-stage re-run cost cache (skip
re-paying for a collection pass on a debug rerun), not inter-stage handoff.
"""
from src.repository.connection import read_only, transactional
from src.shared.decorators import logged


class RawPassRepository:

    @read_only
    def get_passes(self, conn, universe_id: int, passes: tuple[int, ...],
                    params: set[str] | None = None) -> dict[int, dict] | None:
        """None unless every requested pass has at least one saved row for
        every name in `params` (when given) — not just "this pass_number
        exists at all". A pass_number existing with only some of the
        expected params present is exactly what a collection-scheme change
        leaves behind (e.g. flags moving from 2 tier-based passes to 1
        boolean-membership pass: pass 2 still has real ordinal rows, but no
        flag rows at all under the new scheme) — treating that as a hit
        crashes downstream (KeyError on a missing param) or, worse, silently
        misinterprets old-shape scores under the new parsing. `params=None`
        keeps the old any-row-at-all check for callers that don't have a
        param list to validate against."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT pass_number, param FROM raw_passes WHERE universe_id = %s AND pass_number = ANY(%s)",
                (universe_id, list(passes)),
            )
            rows = cur.fetchall()
        present_passes = {p for p, _ in rows}
        if present_passes != set(passes):
            return None
        if params is not None:
            params_by_pass: dict[int, set] = {p: set() for p in passes}
            for p, param in rows:
                params_by_pass[p].add(param)
            if any(not params.issubset(params_by_pass[p]) for p in passes):
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

    @logged(lambda _, self, universe_id, pass_number, scores_by_param:
            f"saved pass {pass_number} raw scores for universe {universe_id} ({len(scores_by_param)} param(s))")
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
