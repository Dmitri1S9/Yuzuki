-- Migration: token_usage table for real per-call Gemini cost tracking (2026-09-23)
-- Every real (non-cache-hit) GeminiClient._request() call logs its actual
-- prompt/output/thinking token counts here — replaces the guessed,
-- prompt-shape-based cost estimates used earlier (see the session that
-- added this: those estimates were off by an unknown, unmeasured margin).
-- Written directly from src/infra/token_usage.py, not through the usual
-- repository layer — telemetry is a cross-cutting concern the same way
-- redis_client.py's cache already reaches into infrastructure straight
-- from the AI client, not a domain object anything else needs to query
-- through CharacterRepository-style abstractions.
-- Not scoped to a universe_id: call_type (rank/flag/relation/group_medium/
-- ...) + model already answer the actual question ("what does a flag call
-- cost"), and avoids threading a new parameter through every single
-- GeminiClient method just for telemetry.
CREATE TABLE token_usage (
    id               BIGSERIAL PRIMARY KEY,
    call_type        TEXT NOT NULL,
    model            TEXT NOT NULL,
    prompt_tokens    INT NOT NULL,
    output_tokens    INT NOT NULL,
    thinking_tokens  INT NOT NULL DEFAULT 0,
    total_tokens     INT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX token_usage_call_type_idx ON token_usage (call_type);
CREATE INDEX token_usage_created_at_idx ON token_usage (created_at);
