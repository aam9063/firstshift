"""Declarative base and engine/session factory for FirstShift's Postgres store."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    """Build a psycopg engine for the given URL."""
    return create_engine(url, pool_pre_ping=True)
