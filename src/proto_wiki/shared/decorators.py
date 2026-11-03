"""Cross-cutting logging decorator, applied only to internal (workhorse)
functions — never to infra/ollama_client.py, the one external-service class.
proto_wiki is its own standalone service (own dependencies, own process,
not part of the main Yuzuki pipeline's image), so this is a self-contained
copy of the same idea, not an import from src.shared.decorators.
"""
import functools
import logging


def logged(build_message, level: int = logging.INFO):
    """build_message(result, *args, **kwargs) -> str | None; None means
    "log nothing" (e.g. only log when something actually changed). `level`
    picks the log level (default INFO) — pass logging.WARNING/logging.ERROR
    for what used to be a log.warning/log.error call. Logs via the
    decorated function's own module logger."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            message = build_message(result, *args, **kwargs)
            if message is not None:
                logging.getLogger(fn.__module__).log(level, message)
            return result
        return wrapper
    return decorator
