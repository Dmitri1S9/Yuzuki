"""Cross-cutting step-logging decorators shared by every pipeline stage.

Stack closest-to-function first: the one right above `def` matters most (it
can change what the step returns), the ones further up matter progressively
less (they only narrate). See ARCHITECTURE.md.
"""
import functools
import logging


def announce(message: str):
    """Least significant layer — logs that a step is starting. Pure
    narration, never changes behavior."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            logging.getLogger(fn.__module__).info(message)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def report(summarize):
    """Logs a one-line summary of a step's result, built from the result by
    `summarize`. Also narration only — never changes the returned value."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            logging.getLogger(fn.__module__).info(summarize(result))
            return result
        return wrapper
    return decorator


def logged(build_message, level: int = logging.INFO):
    """Like `report`, but the message can also use the call's own arguments,
    not just the result — for internal workhorse methods (repository writes,
    etc.) whose useful summary needs args (`name`, `universe_id`, ...), not
    just a return value. `build_message(result, *args, **kwargs) -> str |
    None`; `None` means "log nothing" (e.g. only log when something actually
    changed). `level` picks the log level (default INFO) — pass
    `logging.WARNING`/`logging.ERROR` for what used to be a `log.warning`/
    `log.error` call, the decorator doesn't infer that from the message.
    Stack above the innermost decorator (`@transactional`/`@read_only`),
    same "closest-to-def matters most" rule as announce/report."""
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
