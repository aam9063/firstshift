"""Shared FastAPI dependencies."""

import os
from collections.abc import Iterator

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.base import make_engine
from app.settings import settings

_ENGINES: dict[str, Engine] = {}


def _engine(url: str) -> Engine:
    """One engine per URL, created lazily and cached for the process."""
    if url not in _ENGINES:
        _ENGINES[url] = make_engine(url)
    return _ENGINES[url]


def get_session() -> Iterator[Session]:
    """Request-scoped session; commits on success, rolls back on error.

    The URL resolves per call (DATABASE_URL env override first, then
    settings) so tests can point the env at a throwaway schema after import,
    the same way tests/test_db_models.py does.
    """
    url = os.environ.get("DATABASE_URL") or settings.database_url
    session = Session(_engine(url))
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
