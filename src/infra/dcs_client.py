"""Pushes draft results to DCS for human review — the counterpart to
src/api/routes/confirm.py, which is where DCS calls back once something is
approved. See ARCHITECTURE.md for the full push -> review -> confirm loop.
"""
import logging

import httpx

from src.infra.settings.config import Settings

log = logging.getLogger(__name__)

_settings = Settings()


def _post(path: str, body: dict) -> dict:
    url = f"{_settings.dcs_url.rstrip('/')}{path}"
    response = httpx.post(url, json=body, timeout=30.0)
    response.raise_for_status()
    return response.json()


def push_roster_draft(universe_id: int, universe_name: str, arc: str | None,
                       roster: list[dict], groups: dict[str, list[dict]]) -> dict:
    return _post("/api/queue/roster", {
        "universe_id": universe_id, "universe_name": universe_name, "arc": arc,
        "payload": {"roster": roster, "groups": groups},
    })


def push_graph_draft(universe_id: int, universe_name: str, arc: str | None,
                      nodes: list[dict], edges: list[dict]) -> dict:
    return _post("/api/queue/graph", {
        "universe_id": universe_id, "universe_name": universe_name, "arc": arc,
        "payload": {"nodes": nodes, "edges": edges},
    })


def push_kappa_report(universe_id: int, universe_name: str, arc: str | None,
                       quality: dict) -> dict:
    return _post("/api/queue/kappa", {
        "universe_id": universe_id, "universe_name": universe_name, "arc": arc,
        "payload": {"quality": quality},
    })
