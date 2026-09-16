"""SQLAlchemy engine, session, and base setup for the expenseflow SQLite database."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = "sqlite:///./expenseflow.db"

engine: Engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal: sessionmaker[Session] = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for a single request, closing it afterward.

    FastAPI dependency: use as `db: Session = Depends(get_db)`.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables registered on Base's metadata if they don't already exist."""
    from app import models  # noqa: F401  (registers ORM models on Base.metadata)

    Base.metadata.create_all(bind=engine)
