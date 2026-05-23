"""Run a single kappa pass synchronously (no Celery).

Usage: python run_kappa_pass.py <pass_number> <output_csv>

  pass_number   1 or 2
  output_csv    e.g. pass1.csv

All data is stored in universe id=30 ("Classroom of the Elite" / "Year 1")
using col_1 / col_2 columns. Different pass numbers produce different Redis
cache keys so the two passes are always independent AI calls.
"""
import os, sys, csv, json, logging
os.environ["REDIS_URL_CACHE"] = "redis://localhost:6379/1"
os.environ["REDIS_URL_CELERY"] = "redis://localhost:6379/0"

import psycopg2
from scipy.stats import norm
from app.settings.config import Settings
from app.apiClients.clientGemini import GeminiClient
from app.apiClients.base_client import hash_args
from app.settings.redis import redis_cache
from db.service import create_universe, save_rank_result, save_flag_result

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

UNIVERSE_NAME = "Classroom of the Elite"
ARC = "Year 1"

FLAG_COLS = [
    "manipulative","honest","impulsive","secretive","self_sacrificing",
    "adaptable","loyal","empathetic","cruel","arrogant","competitive",
    "ruthless","is_strategist","has_humor",
    "is_physically_attractive","is_intimidating","is_muscular",
    "has_distinctive_feature","is_well_groomed",
    "goal_power","goal_love","goal_knowledge","goal_revenge",
    "goal_survival","goal_duty","goal_freedom","goal_recognition","goal_protection",
    "military","politics","science","art","education","crime","commerce",
    "has_magic","has_tragic_past","is_strong_willed","is_provocative",
    "is_loner","is_unstable","is_fanatical",
    "is_idealist","is_nihilist","is_pragmatist","is_hedonist",
    "is_machiavellian","is_revolutionary","is_fatalist",
    "has_physical_weakness","has_psychological_weakness",
]

RANK_PROMPTS = {
    "combat_potential": "user_prompt_combat_potential",
    "intellect":        "user_prompt_intellect_potential",
    "authority_scope":  "user_prompt_authority_scope",
    "loyalty_command":  "user_prompt_loyalty_command",
    "social_impact":    "user_prompt_social_impact",
    "wealth":           "user_prompt_wealth",
}

ALL_COLS = FLAG_COLS + list(RANK_PROMPTS.keys())


def within_normal(i: int, N: int) -> float:
    if N <= 1:
        return 0.5
    z = (i - (N + 1) / 2) / ((N - 1) / 6)
    return float(norm.cdf(z))


def compute_score(position, segment_counts: list) -> float | None:
    if position is None or not segment_counts:
        return None
    cumulative = 0
    for tier_idx, count in enumerate(segment_counts):
        if position < cumulative + count:
            return round(tier_idx * 10 + within_normal(position - cumulative + 1, count), 4)
        cumulative += count
    return None


def main():
    pass_number = int(sys.argv[1])
    out = sys.argv[2]
    assert pass_number in (1, 2), "pass_number must be 1 or 2"

    with open("app/data/characters_cote.json", encoding="utf-8") as f:
        characters = json.load(f)["Start of Year 1 (Y1V1)"]

    log.info("Pass %d | arc='%s' | chars=%d | output='%s'", pass_number, ARC, len(characters), out)

    universe_id = create_universe(UNIVERSE_NAME, characters, ARC)
    log.info("Universe id=%d", universe_id)

    # Use pass_number as part of a salt so cache keys differ between passes
    arc_salt = f"{ARC} [K{pass_number}]"
    client = GeminiClient()

    for param, prompt_key in RANK_PROMPTS.items():
        log.info("  rank  %s ...", param)
        key = f"rank:{hash_args(prompt_key, characters, UNIVERSE_NAME, arc_salt, None)}"
        redis_cache.delete(key)
        result = client.rank(prompt_key, characters, UNIVERSE_NAME, arc_salt)
        save_rank_result(result, universe_id, param, pass_number=pass_number)

    for flag in FLAG_COLS:
        log.info("  flag  %s ...", flag)
        key = f"flag:{hash_args(flag, characters, UNIVERSE_NAME, arc_salt, None)}"
        redis_cache.delete(key)
        result = client.flag(flag, characters, UNIVERSE_NAME, arc_salt)
        save_flag_result(result, universe_id, flag, pass_number=pass_number)

    log.info("All tasks done. Exporting CSV...")

    s = Settings()
    conn = psycopg2.connect(host=s.db_host, port=s.db_port,
                            dbname=s.db_name, user=s.db_user, password=s.db_password)
    with conn.cursor() as cur:
        cols_sql = ", ".join(f"c.{col}_{pass_number}" for col in ALL_COLS)
        cur.execute(
            f"SELECT c.name, {cols_sql} FROM characters c WHERE c.universe_id=%s ORDER BY c.name",
            (universe_id,)
        )
        char_rows = cur.fetchall()

        uni_sql = ", ".join(f"u.{col}_{pass_number}" for col in ALL_COLS)
        cur.execute(f"SELECT {uni_sql} FROM universes u WHERE u.id=%s", (universe_id,))
        uni = cur.fetchone()
    conn.close()

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["entity"] + ALL_COLS)
        writer.writeheader()
        for row in char_rows:
            d = {"entity": row[0]}
            for i, col in enumerate(ALL_COLS):
                raw_pos = row[i + 1]
                raw_seg = uni[i]
                seg = raw_seg if isinstance(raw_seg, list) else (json.loads(raw_seg) if raw_seg else [])
                score = compute_score(raw_pos, seg)
                d[col] = score if score is not None else "None"
            writer.writerow(d)

    log.info("Exported %d characters -> %s", len(char_rows), out)
    print(f"Done: {len(char_rows)} characters -> {out}")


if __name__ == "__main__":
    main()
