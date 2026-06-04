"""SQLAlchemy 2.0 engine, session factory, and declarative Base.

All ORM models inherit from `Base`. Request handlers acquire a session
via the `get_db` FastAPI dependency, which guarantees the session is
closed even if the handler raises.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,  # transparently recover dropped connections
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models (SQLAlchemy 2.0 style)."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
