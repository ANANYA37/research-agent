"""Persistent research history storage backed by SQLite."""

import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from semantic_cache import cosine_similarity, embed_text


DATA_DIR = Path(__file__).resolve().parent / "data"
DB_FILE = DATA_DIR / "research_history.sqlite3"
LEGACY_JSON_FILE = DATA_DIR / "research_history.json"
MAX_HISTORY_ITEMS = 50
SEMANTIC_CACHE_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.55"))
_LOCK = threading.Lock()
_INITIALIZED = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.strip().lower())


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _database():
    connection = _connect()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _row_to_item(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "topic": row["topic"],
        "normalized_topic": row["normalized_topic"],
        "depth": row["depth"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "report": row["report"],
        "sources": json.loads(row["sources_json"] or "[]"),
        "queries_used": json.loads(row["queries_used_json"] or "[]"),
        "iterations_completed": row["iterations_completed"],
        "topic_embedding": json.loads(row["topic_embedding_json"] or "[]"),
        "citation_verification": json.loads(row["citation_verification_json"] or "{}"),
    }


def _load_legacy_history() -> list[dict]:
    if not LEGACY_JSON_FILE.exists():
        return []

    try:
        with LEGACY_JSON_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _insert_item(connection: sqlite3.Connection, item: dict) -> None:
    connection.execute(
        """
        INSERT INTO research_history (
            id,
            topic,
            normalized_topic,
            depth,
            created_at,
            updated_at,
            report,
            sources_json,
            queries_used_json,
            iterations_completed,
            topic_embedding_json,
            citation_verification_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(normalized_topic, depth) DO UPDATE SET
            topic = excluded.topic,
            updated_at = excluded.updated_at,
            report = excluded.report,
            sources_json = excluded.sources_json,
            queries_used_json = excluded.queries_used_json,
            iterations_completed = excluded.iterations_completed,
            topic_embedding_json = excluded.topic_embedding_json,
            citation_verification_json = excluded.citation_verification_json
        """,
        (
            item.get("id") or str(uuid4()),
            item.get("topic", "").strip(),
            item.get("normalized_topic") or _normalize_topic(item.get("topic", "")),
            item.get("depth", 3),
            item.get("created_at") or _now_iso(),
            item.get("updated_at") or _now_iso(),
            item.get("report", ""),
            json.dumps(item.get("sources", []), ensure_ascii=False),
            json.dumps(item.get("queries_used", []), ensure_ascii=False),
            item.get("iterations_completed", 0),
            json.dumps(item.get("topic_embedding") or embed_text(item.get("topic", ""))),
            json.dumps(item.get("citation_verification", {}), ensure_ascii=False),
        ),
    )


def _trim_history(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        DELETE FROM research_history
        WHERE id NOT IN (
            SELECT id
            FROM research_history
            ORDER BY updated_at DESC
            LIMIT ?
        )
        """,
        (MAX_HISTORY_ITEMS,),
    )


def _initialize() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    with _LOCK:
        if _INITIALIZED:
            return

        with _database() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_history (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    normalized_topic TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    report TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    queries_used_json TEXT NOT NULL,
                    iterations_completed INTEGER NOT NULL DEFAULT 0,
                    topic_embedding_json TEXT NOT NULL DEFAULT '[]',
                    citation_verification_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(normalized_topic, depth)
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(research_history)").fetchall()
            }
            if "topic_embedding_json" not in columns:
                connection.execute(
                    "ALTER TABLE research_history ADD COLUMN topic_embedding_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "citation_verification_json" not in columns:
                connection.execute(
                    "ALTER TABLE research_history ADD COLUMN citation_verification_json TEXT NOT NULL DEFAULT '{}'"
                )
            rows_missing_embeddings = connection.execute(
                """
                SELECT id, topic
                FROM research_history
                WHERE topic_embedding_json = '[]' OR topic_embedding_json = ''
                """
            ).fetchall()
            for row in rows_missing_embeddings:
                connection.execute(
                    """
                    UPDATE research_history
                    SET topic_embedding_json = ?
                    WHERE id = ?
                    """,
                    (json.dumps(embed_text(row["topic"])), row["id"]),
                )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_research_history_updated_at
                ON research_history(updated_at DESC)
                """
            )

            has_rows = connection.execute("SELECT 1 FROM research_history LIMIT 1").fetchone()
            if not has_rows:
                for item in _load_legacy_history():
                    _insert_item(connection, item)
                _trim_history(connection)

        _INITIALIZED = True


def list_history() -> list[dict]:
    """Return all saved research items, newest first."""
    _initialize()

    with _LOCK, _database() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM research_history
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (MAX_HISTORY_ITEMS,),
        ).fetchall()
        return [_row_to_item(row) for row in rows]


def get_history_item(item_id: str) -> dict | None:
    """Return one saved research item by id."""
    _initialize()

    with _LOCK, _database() as connection:
        row = connection.execute(
            "SELECT * FROM research_history WHERE id = ?",
            (item_id,),
        ).fetchone()
        return _row_to_item(row) if row else None


def find_cached_research(topic: str, depth: int) -> dict | None:
    """Return exact or semantically similar research from saved history."""
    _initialize()

    normalized_topic = _normalize_topic(topic)
    query_embedding = embed_text(topic)

    with _LOCK, _database() as connection:
        # First preference: exact topic and exact depth.
        row = connection.execute(
            """
            SELECT *
            FROM research_history
            WHERE normalized_topic = ? AND depth = ?
            """,
            (normalized_topic, depth),
        ).fetchone()
        if row:
            return _row_to_item(row)

        # Second preference: exact topic at any depth. Users expect identical
        # searches to reuse previous reports even if the depth slider changed.
        row = connection.execute(
            """
            SELECT *
            FROM research_history
            WHERE normalized_topic = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (normalized_topic,),
        ).fetchone()
        if row:
            item = _row_to_item(row)
            item["cache_similarity"] = 1.0
            return item

        rows = connection.execute(
            """
            SELECT *
            FROM research_history
            WHERE depth = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (depth, MAX_HISTORY_ITEMS),
        ).fetchall()

        best_item = None
        best_score = 0.0
        for candidate in rows:
            item = _row_to_item(candidate)
            score = cosine_similarity(query_embedding, item.get("topic_embedding") or [])
            if score > best_score:
                best_item = item
                best_score = score

        if best_item and best_score >= SEMANTIC_CACHE_THRESHOLD:
            best_item["cache_similarity"] = round(best_score, 4)
            return best_item

        # Final fallback: semantically similar topic at a different depth. This
        # favors reuse over duplicate research while still requiring similarity.
        rows = connection.execute(
            """
            SELECT *
            FROM research_history
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (MAX_HISTORY_ITEMS,),
        ).fetchall()

        best_item = None
        best_score = 0.0
        for candidate in rows:
            item = _row_to_item(candidate)
            score = cosine_similarity(query_embedding, item.get("topic_embedding") or [])
            if score > best_score:
                best_item = item
                best_score = score

        if best_item and best_score >= SEMANTIC_CACHE_THRESHOLD:
            best_item["cache_similarity"] = round(best_score, 4)
            return best_item
        return None


def save_research(topic: str, depth: int, result: dict) -> dict:
    """Create or update a saved research item for the topic/depth pair."""
    _initialize()

    normalized_topic = _normalize_topic(topic)
    now = _now_iso()

    with _LOCK, _database() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM research_history
            WHERE normalized_topic = ? AND depth = ?
            """,
            (normalized_topic, depth),
        ).fetchone()

        saved_item = {
            "id": existing["id"] if existing else str(uuid4()),
            "topic": topic.strip(),
            "normalized_topic": normalized_topic,
            "depth": depth,
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
            "report": result.get("report", ""),
            "sources": result.get("sources", []),
            "queries_used": result.get("queries_used", []),
            "iterations_completed": result.get("iterations_completed", 0),
            "topic_embedding": embed_text(topic),
            "citation_verification": result.get("citation_verification", {}),
        }

        _insert_item(connection, saved_item)
        _trim_history(connection)

    return saved_item


# SQLAlchemy-backed, account-aware implementations.  These intentionally
# override the legacy SQLite helpers above while retaining the same response
# shape for existing API consumers.
from sqlalchemy import select

from database import SessionLocal
from db_models import Collection, ResearchHistory, Tag


def _orm_item_to_dict(item: ResearchHistory) -> dict:
    return {
        "id": item.id,
        "topic": item.topic,
        "normalized_topic": item.normalized_topic,
        "depth": item.depth,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "report": item.report,
        "sources": item.sources or [],
        "queries_used": item.queries_used or [],
        "iterations_completed": item.iterations_completed,
        "topic_embedding": item.topic_embedding or [],
        "citation_verification": item.citation_verification or {},
        "collections": [{"id": value.id, "name": value.name} for value in item.collections],
        "tags": [{"id": value.id, "name": value.name, "color": value.color} for value in item.tags],
    }


def list_history(user_id: str) -> list[dict]:
    with SessionLocal() as session:
        items = session.scalars(
            select(ResearchHistory).where(ResearchHistory.user_id == user_id)
            .order_by(ResearchHistory.updated_at.desc()).limit(MAX_HISTORY_ITEMS)
        ).all()
        return [_orm_item_to_dict(item) for item in items]


def get_history_item(user_id: str, item_id: str) -> dict | None:
    with SessionLocal() as session:
        item = session.scalar(select(ResearchHistory).where(
            ResearchHistory.id == item_id, ResearchHistory.user_id == user_id
        ))
        return _orm_item_to_dict(item) if item else None


def find_cached_research(user_id: str, topic: str, depth: int) -> dict | None:
    normalized_topic = _normalize_topic(topic)
    query_embedding = embed_text(topic)
    with SessionLocal() as session:
        item = session.scalar(select(ResearchHistory).where(
            ResearchHistory.user_id == user_id,
            ResearchHistory.normalized_topic == normalized_topic,
            ResearchHistory.depth == depth,
        ))
        if item:
            response = _orm_item_to_dict(item)
            response["cache_similarity"] = 1.0
            return response
        candidates = session.scalars(select(ResearchHistory).where(
            ResearchHistory.user_id == user_id
        ).order_by(ResearchHistory.updated_at.desc()).limit(MAX_HISTORY_ITEMS)).all()
        best, score = None, 0.0
        for candidate in candidates:
            candidate_score = cosine_similarity(query_embedding, candidate.topic_embedding or [])
            if candidate_score > score:
                best, score = candidate, candidate_score
        if best and score >= SEMANTIC_CACHE_THRESHOLD:
            response = _orm_item_to_dict(best)
            response["cache_similarity"] = round(score, 4)
            return response
    return None


def save_research(user_id: str, topic: str, depth: int, result: dict) -> dict:
    normalized_topic = _normalize_topic(topic)
    with SessionLocal() as session:
        item = session.scalar(select(ResearchHistory).where(
            ResearchHistory.user_id == user_id,
            ResearchHistory.normalized_topic == normalized_topic,
            ResearchHistory.depth == depth,
        ))
        if item is None:
            item = ResearchHistory(user_id=user_id, topic=topic.strip(), normalized_topic=normalized_topic, depth=depth)
            session.add(item)
        item.topic = topic.strip()
        item.report = result.get("report", "")
        item.sources = result.get("sources", [])
        item.queries_used = result.get("queries_used", [])
        item.iterations_completed = result.get("iterations_completed", 0)
        item.topic_embedding = embed_text(topic)
        item.citation_verification = result.get("citation_verification", {})
        session.commit()
        session.refresh(item)
        return _orm_item_to_dict(item)


def list_collections(user_id: str) -> list[dict]:
    with SessionLocal() as session:
        rows = session.scalars(select(Collection).where(Collection.user_id == user_id).order_by(Collection.name)).all()
        return [{"id": row.id, "name": row.name, "description": row.description, "report_count": len(row.reports)} for row in rows]


def create_collection(user_id: str, name: str, description: str = "") -> dict:
    with SessionLocal() as session:
        row = Collection(user_id=user_id, name=name.strip(), description=description.strip())
        session.add(row)
        session.commit()
        return {"id": row.id, "name": row.name, "description": row.description, "report_count": 0}


def list_tags(user_id: str) -> list[dict]:
    with SessionLocal() as session:
        rows = session.scalars(select(Tag).where(Tag.user_id == user_id).order_by(Tag.name)).all()
        return [{"id": row.id, "name": row.name, "color": row.color, "report_count": len(row.reports)} for row in rows]


def create_tag(user_id: str, name: str, color: str = "#2563eb") -> dict:
    with SessionLocal() as session:
        row = Tag(user_id=user_id, name=name.strip(), color=color)
        session.add(row)
        session.commit()
        return {"id": row.id, "name": row.name, "color": row.color, "report_count": 0}


def assign_report_metadata(user_id: str, item_id: str, collection_ids: list[str], tag_ids: list[str]) -> dict | None:
    with SessionLocal() as session:
        item = session.scalar(select(ResearchHistory).where(
            ResearchHistory.id == item_id, ResearchHistory.user_id == user_id
        ))
        if not item:
            return None
        collections = session.scalars(select(Collection).where(
            Collection.user_id == user_id, Collection.id.in_(collection_ids)
        )).all() if collection_ids else []
        tags = session.scalars(select(Tag).where(
            Tag.user_id == user_id, Tag.id.in_(tag_ids)
        )).all() if tag_ids else []
        if len(collections) != len(set(collection_ids)) or len(tags) != len(set(tag_ids)):
            raise ValueError("Collections and tags must belong to the current user")
        item.collections, item.tags = collections, tags
        session.commit()
        session.refresh(item)
        return _orm_item_to_dict(item)
