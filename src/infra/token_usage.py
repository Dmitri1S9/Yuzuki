"""Real per-call Gemini token usage, logged straight from GeminiClient._request()
— replaces the guessed, prompt-shape-based cost estimates used earlier in
this project's life with actual response.usage_metadata numbers. A
cross-cutting concern, not a domain object: writes directly via its own
psycopg2 connection rather than going through the usual repository layer
(same reasoning redis_client.py already applies to the cache — telemetry
reaches into infrastructure straight from the AI client).

A write failure here must never break the actual Gemini call or the
pipeline it's part of — every write is best-effort, caught and logged, not
raised.
"""
import logging

import psycopg2

from src.infra.settings.config import Settings

log = logging.getLogger(__name__)
_settings = Settings()


def log_token_usage(call_type: str, model: str, prompt_tokens: int, output_tokens: int,
                     thinking_tokens: int, total_tokens: int) -> None:
    try:
        conn = psycopg2.connect(
            dbname=_settings.db_name, user=_settings.db_user, password=_settings.db_password,
            host=_settings.db_host, port=_settings.db_port,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO token_usage (call_type, model, prompt_tokens, output_tokens, "
                    "thinking_tokens, total_tokens) VALUES (%s, %s, %s, %s, %s, %s)",
                    (call_type, model, prompt_tokens, output_tokens, thinking_tokens, total_tokens),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        log.warning("failed to log token usage for call_type=%r model=%r (non-fatal)", call_type, model,
                    exc_info=True)
