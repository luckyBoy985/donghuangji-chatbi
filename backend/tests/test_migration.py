import sqlite3

from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.models.entities import Conversation
from backend.app.models.identity import User
from backend.app.services.migration.legacy import migrate_legacy


def _legacy_db(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE conversation (
            id TEXT PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE message (
            id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT,
            status TEXT, generation_status TEXT, model TEXT, filters_json TEXT,
            created_at TEXT
        );
        CREATE TABLE citation (
            id TEXT PRIMARY KEY, message_id TEXT, citation_key TEXT,
            chunk_id TEXT, doc_id TEXT, product TEXT, section TEXT, title TEXT,
            source_type TEXT, published_at TEXT, url TEXT, snippet TEXT,
            score REAL, used_in_answer INTEGER
        );
        CREATE TABLE report (
            id TEXT PRIMARY KEY, conversation_id TEXT, title TEXT,
            products_json TEXT, markdown TEXT, html TEXT, created_at TEXT
        );
        INSERT INTO conversation VALUES
            ('conv-1', '旧会话', '2026-10-01', '2026-10-02');
        INSERT INTO message VALUES
            ('msg-1', 'conv-1', 'user', '问题', 'completed', 'none', 'deepseek-chat',
             '{"products":["东煌纪"],"sections":[]}', '2026-10-01');
        INSERT INTO citation VALUES
            ('cit-1', 'msg-1', 'S1', 'chunk-1', 'doc-1', '东煌纪', '产品资料',
             '资料', 'internal', '', '', '片段', 0.9, 1);
        INSERT INTO report VALUES
            ('rep-1', 'conv-1', '旧报告', '["东煌纪"]', '# 报告', '<h1>报告</h1>',
             '2026-10-02');
        """
    )
    connection.commit()
    connection.close()


def test_legacy_migration_preserves_ids_and_is_idempotent(
    tmp_path, session_factory
):
    source = tmp_path / "legacy.db"
    _legacy_db(source)
    db = session_factory()
    owner = User(
        username="admin",
        display_name="Admin",
        password_hash=hash_password("CorrectHorseBatteryStaple"),
        platform_role="admin",
    )
    db.add(owner)
    db.commit()
    owner_id = owner.id
    db.close()

    first = migrate_legacy(source, session_factory, owner_username="admin")
    second = migrate_legacy(source, session_factory, owner_username="admin")

    assert first["conversations"] == 1
    assert first["messages"] == 1
    assert first["citations"] == 1
    assert first["reports"] == 1
    assert second["skipped"] is True
    db = session_factory()
    conversation = db.scalar(select(Conversation).where(Conversation.id == "conv-1"))
    assert conversation.owner_user_id == owner_id
    assert db.query(Conversation).count() == 1
    db.close()
