import logging, os, sys

_configured = False

def setup_logging():
    global _configured
    if _configured:
        return
    _configured = True

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    lvl = getattr(logging, level, logging.INFO)

    logging.basicConfig(
        level=lvl,
        stream=sys.stdout,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )

    for name, obj in logging.root.manager.loggerDict.items():
        if isinstance(obj, logging.Logger) and name.startswith("app"):
            obj.handlers.clear()
            obj.propagate = True
            obj.setLevel(lvl)


    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "celery", "kombu"):
        lg = logging.getLogger(name)
        lg.propagate = False
        lg.setLevel(lvl)
