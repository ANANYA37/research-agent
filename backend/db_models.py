"""SQLAlchemy models for accounts and user-owned research data."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Table, Text, UniqueConstraint, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


report_collections = Table(
    "report_collections",
    Base.metadata,
    Column("report_id", String(36), ForeignKey("research_history.id", ondelete="CASCADE"), primary_key=True),
    Column("collection_id", String(36), ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
)

report_tags = Table(
    "report_tags",
    Base.metadata,
    Column("report_id", String(36), ForeignKey("research_history.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class BaseModel(Base):
    __abstract__ = True


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reports: Mapped[list["ResearchHistory"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class ResearchHistory(Base):
    __tablename__ = "research_history"
    __table_args__ = (UniqueConstraint("user_id", "normalized_topic", "depth", name="uq_user_topic_depth"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(Text)
    normalized_topic: Mapped[str] = mapped_column(Text, index=True)
    depth: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)
    report: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)
    queries_used: Mapped[list] = mapped_column(JSON, default=list)
    iterations_completed: Mapped[int] = mapped_column(Integer, default=0)
    topic_embedding: Mapped[list] = mapped_column(JSON, default=list)
    citation_verification: Mapped[dict] = mapped_column(JSON, default=dict)
    owner: Mapped[User] = relationship(back_populates="reports")
    collections: Mapped[list["Collection"]] = relationship(secondary=report_collections, back_populates="reports")
    tags: Mapped[list["Tag"]] = relationship(secondary=report_tags, back_populates="reports")


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_collection_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reports: Mapped[list[ResearchHistory]] = relationship(secondary=report_collections, back_populates="collections")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tag_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(48))
    color: Mapped[str] = mapped_column(String(7), default="#2563eb")
    reports: Mapped[list[ResearchHistory]] = relationship(secondary=report_tags, back_populates="tags")


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "report_id", name="uq_watch_user_report"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(String(36))
    topic: Mapped[str] = mapped_column(Text)
    depth: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[str] = mapped_column(String(12), default="weekly")
    paused: Mapped[int] = mapped_column(Integer, default=0)
    unread: Mapped[int] = mapped_column(Integer, default=0)
    next_check: Mapped[float] = mapped_column(Float, index=True)
    last_check: Mapped[float] = mapped_column(Float, default=0)
    active_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    runs: Mapped[list["WatchlistRun"]] = relationship(cascade="all, delete-orphan", order_by="WatchlistRun.created_at.desc()")


class WatchlistRun(Base):
    __tablename__ = "watchlist_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    watchlist_id: Mapped[str] = mapped_column(String(36), ForeignKey("watchlists.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")

