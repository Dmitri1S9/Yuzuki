"""Ordinal/flag pass collection and CSV round-trip. Parameter names come from
src.domain.parameters (the single source of truth) — not hardcoded here.
"""
import csv
import logging
import re

from scipy.stats import norm

from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS
from src.infra.ai_clients.gemini_client import GeminiClient
from src.services.collection.features.constants import ARC, PASSES, SLUG, UNIVERSE_NAME
from src.shared.paths import run_path

log = logging.getLogger(__name__)


def create_client() -> GeminiClient:
    return GeminiClient()


def within_normal(i: int, n: int) -> float:
    if n <= 1:
        return 0.5
    z = (i - (n + 1) / 2) / ((n - 1) / 6)
    return float(norm.cdf(z))


def compute_score(position, segment_counts):
    if position is None or not segment_counts:
        return None
    cumulative = 0
    for tier_idx, count in enumerate(segment_counts):
        if position < cumulative + count:
            return round(tier_idx * 10 + within_normal(position - cumulative + 1, count), 4)
        cumulative += count
    return None


def parse_sorted(sorted_list, marker_re):
    positions, segments = {}, []
    current = position = 0
    for item in sorted_list:
        item = item.strip()
        if not item:
            continue
        if marker_re.match(item):
            segments.append(current)
            current = 0
        else:
            positions[item] = position
            position += 1
            current += 1
    segments.append(current)
    return positions, segments


def scores_from_result(result, marker_re, roster):
    positions, segments = parse_sorted(result["sorted"], marker_re)
    return {name: compute_score(positions.get(name), segments) for name in roster}


def collect(client, roster):
    rank_re = re.compile(r"^T\d+$")
    per_pass = {p: {} for p in PASSES}
    for param, prompt in ORDINAL_PARAMS.items():
        for p in PASSES:
            log.info("rank %-18s pass=%d", param, p)
            result = client.rank(prompt, roster, UNIVERSE_NAME, ARC, pass_number=p)
            per_pass[p][param] = scores_from_result(result, rank_re, roster)
    for flag in FLAG_PARAMS:
        for p in PASSES:
            log.info("flag %-18s pass=%d", flag, p)
            result = client.flag(flag, roster, UNIVERSE_NAME, ARC, pass_number=p)
            per_pass[p][flag] = scores_from_result(result, rank_re, roster)
    return per_pass


def load_per_pass_from_csv(roster, params):
    per_pass = {p: {} for p in PASSES}
    for p in PASSES:
        with open(run_path(f"pass{p}_{SLUG}.csv"), encoding="utf-8") as f:
            rows = {row["entity"]: row for row in csv.DictReader(f)}
        for param in params:
            per_pass[p][param] = {}
            for name in roster:
                raw = rows.get(name, {}).get(param)
                per_pass[p][param][name] = None if raw in (None, "", "None") else float(raw)
    return per_pass


def write_pass_csvs(per_pass, roster, params):
    for p in PASSES:
        with open(run_path(f"pass{p}_{SLUG}.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["entity"] + params)
            writer.writeheader()
            for name in roster:
                row = {"entity": name}
                for param in params:
                    score = per_pass[p][param][name]
                    row[param] = score if score is not None else "None"
                writer.writerow(row)
        log.info("wrote pass%d_%s.csv", p, SLUG)
