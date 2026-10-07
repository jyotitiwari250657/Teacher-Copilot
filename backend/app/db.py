"""Database engine, session factory and FastAPI dependency."""
from __future__ import annotations

from typing import Iterator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    # FastAPI serves requests from a threadpool, so the connection must be
    # safe to share across threads.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    echo=False,
)

# An in-memory SQLite database must reuse a single connection or each thread
# would get its own (empty) database.
if _is_sqlite and ":memory:" in settings.database_url:
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )


def create_db_and_tables() -> None:
    """Create every table declared on the SQLModel metadata."""
    from . import models  # noqa: F401  (register tables before creating)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with Session(engine) as session:
        yield session
