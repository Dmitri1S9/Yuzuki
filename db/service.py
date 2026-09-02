import re
import json
import logging

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from app.serviceExceptions import falseGroupTypeException

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analytics helpers
# ---------------------------------------------------------------------------

def compute_percentile(position: int | None, universe_size: int) -> float | None:
    """Map ordinal position (0-based) to [0.0, 1.0] percentile.

    Normalises across universes of different sizes so cross-arc deltas
    are comparable (e.g. pos=35/37 ≈ pos=63/65 ≈ 0.97).
    Returns None when position is NULL (character not ranked).
    """
    if position is None or universe_size <= 1:
        return None
    return round(position / (universe_size - 1), 4)


def compute_percentile_delta(
    pos_a: int | None, size_a: int,
    pos_b: int | None, size_b: int,
) -> float | None:
    """Percentile difference between two arcs for the same character+param.

    Positive = character rose in ranking, negative = fell.
    Returns None if either position is unknown.
    """
    pct_a = compute_percentile(pos_a, size_a)
    pct_b = compute_percentile(pos_b, size_b)
    if pct_a is None or pct_b is None:
        return None
    return round(pct_b - pct_a, 4)


# ---------------------------------------------------------------------------
# Valid column names (whitelist — prevents SQL injection)
# ---------------------------------------------------------------------------

ORDINAL_PARAMS: set[str] = {
    "combat_potential", "intellect", "authority_scope",
    "loyalty_command", "social_impact", "wealth",
}

FLAG_PARAMS: set[str] = {
    "manipulative", "honest", "impulsive", "secretive", "self_sacrificing",
    "adaptable", "loyal", "empathetic", "cruel", "arrogant", "competitive", "ruthless",
    "is_strategist", "has_humor",
    "is_physically_attractive", "is_intimidating", "is_muscular",
    "has_distinctive_feature", "is_well_groomed",
    "goal_power", "goal_love", "goal_knowledge", "goal_revenge",
    "goal_survival", "goal_duty", "goal_freedom", "goal_recognition", "goal_protection",
    "military", "politics", "science", "art", "education", "crime", "commerce",
    "has_magic", "has_tragic_past", "is_strong_willed",
    "is_provocative", "is_loner", "is_unstable", "is_fanatical",
    "is_idealist", "is_nihilist", "is_pragmatist",
    "is_hedonist", "is_machiavellian", "is_revolutionary", "is_fatalist",
    "has_physical_weakness", "has_psychological_weakness",
}

TIER_RE = re.compile(r"^T(\d+):\s*(.*)")
T0_MARKER = "T0"
T1_MARKER = "T1"

GROUP_CALL_TYPES: set[str] = {"small", "medium", "large", "isolates"}


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _connect() -> psycopg2.extensions.connection:
    from app.settings.config import Settings
    settings = Settings()
    return psycopg2.connect(
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
    )


def _validate_col(name: str, allowed: set[str]) -> None:
    if name not in allowed:
        raise ValueError(f"Invalid column: {name}")


# ---------------------------------------------------------------------------
# Create universe + characters (all NULLs)
# ---------------------------------------------------------------------------

def create_universe(name: str, characters: list[str], arc: str | None = None) -> int:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO universes (name, arc, character_count)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (name, arc) DO UPDATE SET character_count = EXCLUDED.character_count
                   RETURNING id""",
                (name, arc or "", len(characters)),
            )
            uid = cur.fetchone()[0]

            for char_name in characters:
                cur.execute(
                    """INSERT INTO characters (universe_id, name)
                       VALUES (%s, %s)
                       ON CONFLICT (universe_id, name) DO NOTHING""",
                    (uid, char_name),
                )
        conn.commit()
        return uid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Save rank result
# Input: {"sorted": ["T1: name, name", "T2: name", "T3: ", ...], "unknown": [...]}
# Character: position in flat list (0-based, skipping tier markers)
# Universe: [count_T1, count_T2, count_T3, ...]
# ---------------------------------------------------------------------------

def save_rank_result(rank_output: dict, universe_id: int, parameter: str,
                     pass_number: int | None = None) -> dict:
    _validate_col(parameter, ORDINAL_PARAMS)
    col = f"{parameter}_{pass_number}" if pass_number else parameter

    sorted_list = rank_output["sorted"]
    unknown = set(n.strip() for n in rank_output.get("unknown", []) if n.strip())

    char_positions: dict[str, int] = {}
    segment_counts: list[int] = []
    current_segment_count = 0
    position = 0

    for item in sorted_list:
        item = item.strip()
        if not item:
            continue
        if re.match(r"^T\d+$", item):
            segment_counts.append(current_segment_count)
            current_segment_count = 0
        else:
            char_positions[item] = position
            position += 1
            current_segment_count += 1

    if current_segment_count > 0:
        segment_counts.append(current_segment_count)

    conn = _connect()
    try:
        with conn.cursor() as cur:
            for name, pos in char_positions.items():
                cur.execute(
                    f"UPDATE characters SET {col} = %s "
                    "WHERE universe_id = %s AND name = %s",
                    (pos, universe_id, name),
                )

            cur.execute(
                f"UPDATE universes SET {col} = %s WHERE id = %s",
                (Json(segment_counts), universe_id),
            )
        conn.commit()
        log.info("Saved rank %s (pass=%s) for universe %s (%d chars)", parameter, pass_number, universe_id, len(char_positions))
        return {"universe_id": universe_id, "parameter": parameter, "status": "saved"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Save single flag result
# Input: {"sorted": ["name", "T0", "name", "T1", "name"], "unknown": [...]}
# Character: position in sorted list (0-based, skipping T0/T1 markers)
# Universe: [count_before_T0, count_between_T0_T1, count_after_T1, count_unknown]
# ---------------------------------------------------------------------------

def save_flag_result(flag_output: dict, universe_id: int, flag_name: str,
                     pass_number: int | None = None) -> dict:
    _validate_col(flag_name, FLAG_PARAMS)
    col = f"{flag_name}_{pass_number}" if pass_number else flag_name

    sorted_list = flag_output["sorted"]
    unknown = [u for u in flag_output.get("unknown", []) if u.strip()]

    char_positions: dict[str, int] = {}
    segment_counts = [0, 0, 0]
    current_segment = 0
    position = 0

    for item in sorted_list:
        if item == T0_MARKER:
            current_segment = 1
            continue
        if item == T1_MARKER:
            current_segment = 2
            continue
        if not item.strip():
            continue
        char_positions[item] = position
        position += 1
        segment_counts[current_segment] += 1

    conn = _connect()
    try:
        with conn.cursor() as cur:
            for name, pos in char_positions.items():
                cur.execute(
                    f"UPDATE characters SET {col} = %s "
                    "WHERE universe_id = %s AND name = %s",
                    (pos, universe_id, name),
                )

            cur.execute(
                f"UPDATE universes SET {col} = %s WHERE id = %s",
                (Json(segment_counts + [len(unknown)]), universe_id),
            )

        conn.commit()
        log.info("Saved flag %s (pass=%s) for universe %s (%d chars)", flag_name, pass_number, universe_id, len(char_positions))
        return {"universe_id": universe_id, "flag": flag_name, "status": "saved"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Save profile result
# Input: {"characters": {"Name": {"body_age": 16, "soul_age": 16, "height": 176, "gender": "male", "species": "human"}, ...}}
# Character: direct values
# Universe: gender_counts, species_counts
# ---------------------------------------------------------------------------

PROFILE_COLS = {"body_age", "soul_age", "gender", "species"}


def save_profile_result(profile_output: dict, universe_id: int) -> dict:
    characters = profile_output["characters"]

    gender_counts: dict[str, int] = {}
    species_counts: dict[str, int] = {}

    conn = _connect()
    try:
        with conn.cursor() as cur:
            for name, profile in characters.items():
                body_age = profile.get("body_age")
                soul_age = profile.get("soul_age")
                gender = profile.get("gender")
                species = profile.get("species")

                cur.execute(
                    "UPDATE characters SET body_age = %s, soul_age = %s, "
                    "gender = %s, species = %s "
                    "WHERE universe_id = %s AND name = %s",
                    (body_age, soul_age, gender, species, universe_id, name),
                )

                if gender:
                    gender_counts[gender] = gender_counts.get(gender, 0) + 1
                if species:
                    species_counts[species] = species_counts.get(species, 0) + 1

            cur.execute(
                "UPDATE universes SET gender_counts = %s, species_counts = %s WHERE id = %s",
                (Json(gender_counts), Json(species_counts), universe_id),
            )

        conn.commit()
        log.info("Saved profile for universe %s (%d chars)", universe_id, len(characters))
        return {"universe_id": universe_id, "status": "saved"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Save group result
# Input: {"groups": [{"name", "group_type", "members", "leader"}, ...], "isolates": [...], "t0": N}
# Each group -> one row in `groups`. Each isolate -> its own single-member
# row with group_type='isolated'. t0 is not persisted (v1).
# ---------------------------------------------------------------------------

def save_group_result(group_output: dict, universe_id: int, group_type: str) -> dict:
    if group_type not in GROUP_CALL_TYPES:
        raise falseGroupTypeException()

    groups = group_output.get("groups", [])
    isolates = group_output.get("isolates", [])

    conn = _connect()
    try:
        with conn.cursor() as cur:
            for group in groups:
                cur.execute(
                    """INSERT INTO groups (universe_id, name, group_type, leader, members)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (universe_id, group["name"], group["group_type"],
                     group.get("leader"), Json(group["members"])),
                )

            for name in isolates:
                cur.execute(
                    """INSERT INTO groups (universe_id, name, group_type, leader, members)
                       VALUES (%s, %s, 'isolated', NULL, %s)""",
                    (universe_id, name, Json([name])),
                )

        conn.commit()
        log.info("Saved %d groups + %d isolates (call=%s) for universe %s",
                  len(groups), len(isolates), group_type, universe_id)
        return {"universe_id": universe_id, "group_type": group_type, "status": "saved"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Build relationship graph
# Stub: collects every character that appears in any saved group for this
# universe, and writes an empty (all-zero) adjacency matrix. No relationship
# logic yet — this only sets up the storage shape for later population.
# ---------------------------------------------------------------------------

def build_relationship_graph(universe_id: int) -> dict:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT members FROM groups WHERE universe_id = %s", (universe_id,))
            rows = cur.fetchall()

            characters: set[str] = set()
            for (members,) in rows:
                members = members if isinstance(members, list) else json.loads(members)
                characters.update(members)
            characters_list = sorted(characters)
            matrix = [[0] * len(characters_list) for _ in range(len(characters_list))]

            cur.execute(
                """INSERT INTO relationship_graphs (universe_id, characters, matrix)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (universe_id) DO UPDATE
                   SET characters = EXCLUDED.characters, matrix = EXCLUDED.matrix""",
                (universe_id, Json(characters_list), Json(matrix)),
            )

        conn.commit()
        log.info("Built relationship graph for universe %s (%d characters)",
                  universe_id, len(characters_list))
        return {"universe_id": universe_id, "characters": len(characters_list), "status": "saved"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

def get_character(character_id: int) -> dict | None:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM characters WHERE id = %s", (character_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_universe(universe_id: int) -> dict | None:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM universes WHERE id = %s", (universe_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_universe_characters(universe_id: int) -> list[dict]:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM characters WHERE universe_id = %s ORDER BY name",
                (universe_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()
