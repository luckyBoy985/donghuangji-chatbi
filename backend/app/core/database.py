from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import settings


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        Path(database_url.removeprefix(prefix)).parent.mkdir(
            parents=True, exist_ok=True
        )


_ensure_sqlite_parent(settings.database_url)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from backend.app.models import audit  # noqa: F401
    from backend.app.models import entities  # noqa: F401
    from backend.app.models import identity  # noqa: F401
    from backend.app.models import ingestion  # noqa: F401
    from backend.app.models.base import Base

    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def database_health(session_factory=SessionLocal) -> dict:
    session = session_factory()
    try:
        session.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "dialect": session.get_bind().dialect.name,
        }
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
