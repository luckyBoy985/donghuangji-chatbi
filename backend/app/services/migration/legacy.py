from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.audit import MigrationRecord
from backend.app.models.entities import Citation, Conversation, Message, Report
from backend.app.models.identity import User


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    cursor = connection.execute(f"SELECT * FROM {table}")
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def migrate_legacy(
    source_path: Path,
    session_factory: sessionmaker[Session],
    *,
    owner_username: str,
) -> dict:
    source_path = Path(source_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"旧 SQLite 不存在：{source_path}")
    source_digest = _source_hash(source_path)
    db = session_factory()
    try:
        previous = db.scalar(
            select(MigrationRecord).where(
                MigrationRecord.source_hash == source_digest,
                MigrationRecord.status == "completed",
            )
        )
        if previous:
            return {
                "skipped": True,
                "source_hash": source_digest,
                "stats": json.loads(previous.stats_json),
            }

        owner = db.scalar(
            select(User).where(User.username == owner_username.lower())
        )
        if not owner:
            raise ValueError(f"目标管理员不存在：{owner_username}")

        readonly_uri = f"{source_path.as_uri()}?mode=ro&immutable=1"
        connection = sqlite3.connect(readonly_uri, uri=True)
        try:
            conversations = _rows(connection, "conversation")
            messages = _rows(connection, "message")
            citations = _rows(connection, "citation")
            reports = _rows(connection, "report")
        finally:
            connection.close()

        existing_ids = set(
            db.scalars(
                select(Conversation.id).where(
                    Conversation.id.in_([row["id"] for row in conversations])
                )
            ).all()
        )
        if existing_ids:
            raise ValueError(f"目标库已存在同名会话 ID：{sorted(existing_ids)}")

        for row in conversations:
            db.add(
                Conversation(
                    id=row["id"],
                    owner_user_id=owner.id,
                    title=row.get("title") or "旧分析",
                    created_at=row.get("created_at") or "",
                    updated_at=row.get("updated_at") or "",
                )
            )
        db.flush()
        for row in messages:
            db.add(
                Message(
                    id=row["id"],
                    conversation_id=row["conversation_id"],
                    role=row.get("role") or "user",
                    content=row.get("content") or "",
                    status=row.get("status") or "completed",
                    generation_status=row.get("generation_status") or "llm",
                    model=row.get("model") or "none",
                    filters_json=row.get("filters_json") or "{}",
                    created_at=row.get("created_at") or "",
                )
            )
        db.flush()
        for row in citations:
            db.add(
                Citation(
                    id=row["id"],
                    message_id=row["message_id"],
                    citation_key=row.get("citation_key") or "",
                    chunk_id=row.get("chunk_id") or "",
                    doc_id=row.get("doc_id") or "",
                    product=row.get("product") or "",
                    section=row.get("section") or "",
                    title=row.get("title") or "",
                    source_type=row.get("source_type") or "",
                    published_at=row.get("published_at") or "",
                    url=row.get("url") or "",
                    snippet=row.get("snippet") or "",
                    score=float(row.get("score") or 0),
                    used_in_answer=bool(row.get("used_in_answer")),
                )
            )
        for row in reports:
            db.add(
                Report(
                    id=row["id"],
                    conversation_id=row["conversation_id"],
                    title=row.get("title") or "旧报告",
                    products_json=row.get("products_json") or "[]",
                    markdown=row.get("markdown") or "",
                    html=row.get("html") or "",
                    created_at=row.get("created_at") or "",
                )
            )
        db.flush()

        counts = {
            "conversations": len(conversations),
            "messages": len(messages),
            "citations": len(citations),
            "reports": len(reports),
        }
        actual = {
            "conversations": db.scalar(select(func.count()).select_from(Conversation)),
            "messages": db.scalar(select(func.count()).select_from(Message)),
            "citations": db.scalar(select(func.count()).select_from(Citation)),
            "reports": db.scalar(select(func.count()).select_from(Report)),
        }
        for key, expected in counts.items():
            if actual[key] < expected:
                raise ValueError(f"迁移对账失败：{key} expected={expected} actual={actual[key]}")
        db.add(
            MigrationRecord(
                source_hash=source_digest,
                status="completed",
                stats_json=json.dumps(counts, ensure_ascii=False),
            )
        )
        db.commit()
        return {"skipped": False, "source_hash": source_digest, **counts}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
