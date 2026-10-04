"""Database configuration shared by the API and background workers."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATA_DIR = Path(__file__).resolve().parent / "data"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'research_agent.sqlite3'}")


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Create the local development schema; production uses Alembic migrations."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    from db_models import BaseModel  # noqa: F401 - imports all model metadata

    Base.metadata.create_all(bind=engine)
