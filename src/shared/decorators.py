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
