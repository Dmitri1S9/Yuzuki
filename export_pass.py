"""Export flag + rank scores for kappa analysis.

Score formula (same for flags and ranks):
  tier * 10 + pnorm((i - (N+1)/2) / ((N-1)/6))

Usage: python export_pass.py <arc> <pass_number> <output_csv>

  arc          e.g. "Year 1"
  pass_number  1 or 2
  output_csv   e.g. pass1.csv
"""
import sys
import csv
import json
import psycopg2
from scipy.stats import norm
from app.settings.config import Settings

FLAG_COLS = [
    "manipulative", "honest", "impulsive", "secretive", "self_sacrificing",
    "adaptable", "loyal", "empathetic", "cruel", "arrogant", "competitive",
    "ruthless", "is_strategist", "has_humor",
    "is_physically_attractive", "is_intimidating", "is_muscular",
    "has_distinctive_feature", "is_well_groomed",
    "goal_power", "goal_love", "goal_knowledge", "goal_revenge",
    "goal_survival", "goal_duty", "goal_freedom", "goal_recognition",
    "goal_protection",
    "military", "politics", "science", "art", "education", "crime", "commerce",
    "has_magic", "has_tragic_past", "is_strong_willed", "is_provocative",
    "is_loner", "is_unstable", "is_fanatical",
    "is_idealist", "is_nihilist", "is_pragmatist", "is_hedonist",
    "is_machiavellian", "is_revolutionary", "is_fatalist",
    "has_physical_weakness", "has_psychological_weakness",
]

RANK_COLS = [
    "combat_potential", "intellect", "authority_scope",
    "loyalty_command", "social_impact", "wealth",
]

ALL_COLS = FLAG_COLS + RANK_COLS


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
            i_in_tier = position - cumulative + 1
            within = within_normal(i_in_tier, count)
            return round(tier_idx * 10 + within, 4)
        cumulative += count
    return None


arc = sys.argv[1]
pass_number = int(sys.argv[2])
out = sys.argv[3]
assert pass_number in (1, 2), "pass_number must be 1 or 2"

s = Settings()
conn = psycopg2.connect(
    host=s.db_host, port=s.db_port,
    dbname=s.db_name, user=s.db_user, password=s.db_password,
)

with conn.cursor() as cur:
    cur.execute(
        "SELECT id FROM universes WHERE name = 'Classroom of the Elite' AND arc = %s",
        (arc,)
    )
    row = cur.fetchone()
    if not row:
        print(f"Universe arc '{arc}' not found"); sys.exit(1)
    uid = row[0]

    cols_sql = ", ".join(f"c.{col}_{pass_number}" for col in ALL_COLS)
    cur.execute(
        f"SELECT c.name, {cols_sql} FROM characters c "
        f"WHERE c.universe_id = %s ORDER BY c.name",
        (uid,)
    )
    char_rows = cur.fetchall()

    uni_sql = ", ".join(f"u.{col}_{pass_number}" for col in ALL_COLS)
    cur.execute(f"SELECT {uni_sql} FROM universes u WHERE u.id = %s", (uid,))
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
            seg = raw_seg if isinstance(raw_seg, list) else \
                  (json.loads(raw_seg) if raw_seg else [])
            score = compute_score(raw_pos, seg)
            d[col] = score if score is not None else "None"
        writer.writerow(d)

print(f"Exported {len(char_rows)} characters -> {out}")
