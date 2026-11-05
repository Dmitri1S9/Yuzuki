"""Shared connection lifecycle for every repository. The connect/commit/
rollback/close boilerplate that used to be copy-pasted into every single
db/service.py function now lives in exactly these two decorators — a
repository method body is never anything but its own SQL.
"""
import functools

import psycopg2

from src.infra.settings.config import Settings


def connect() -> psycopg2.extensions.connection:
    settings = Settings()
    return psycopg2.connect(
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
    )


def transactional(fn):
    """Wraps a write method: opens a connection, passes it as the method's
    first argument after self, commits on success, rolls back and re-raises
    on failure, always closes."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        conn = connect()
        try:
            result = fn(self, conn, *args, **kwargs)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return wrapper


def read_only(fn):
    """Wraps a read method: opens a connection, passes it as the method's
    first argument after self, always closes; no commit/rollback needed."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        conn = connect()
        try:
            return fn(self, conn, *args, **kwargs)
        finally:
            conn.close()
    return wrapper


def validate_column(name: str, allowed: set[str]) -> None:
    if name not in allowed:
        raise ValueError(f"Invalid column: {name}")
