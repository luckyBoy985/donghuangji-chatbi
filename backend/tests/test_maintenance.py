from backend.app.models.audit import AuditLog
from backend.app.models.identity import LoginAttempt
from backend.app.models.ingestion import IngestJob
from backend.app.services.maintenance import (
    cleanup_audit_logs,
    cleanup_login_attempts,
    mark_stale_jobs_failed,
)


def test_cleanup_audit_logs_removes_only_expired_rows(session_factory):
    db = session_factory()
    db.add_all(
        [
            AuditLog(
                action="old",
                resource_type="test",
                created_at="2025-01-01T00:00:00+00:00",
            ),
            AuditLog(
                action="current",
                resource_type="test",
                created_at="2026-10-24T00:00:00+00:00",
            ),
        ]
    )
    db.commit()

    removed = cleanup_audit_logs(
        db,
        before="2026-01-01T00:00:00+00:00",
    )

    assert removed == 1
    assert [row.action for row in db.query(AuditLog).all()] == ["current"]
    db.close()


def test_cleanup_login_attempts_removes_expired_hashes(session_factory):
    db = session_factory()
    db.add_all(
        [
            LoginAttempt(
                attempt_key="old-key",
                failed_at="2025-01-01T00:00:00+00:00",
            ),
            LoginAttempt(
                attempt_key="current-key",
                failed_at="2026-10-24T00:00:00+00:00",
            ),
        ]
    )
    db.commit()

    removed = cleanup_login_attempts(
        db,
        before="2026-01-01T00:00:00+00:00",
    )

    assert removed == 1
    assert [row.attempt_key for row in db.query(LoginAttempt).all()] == [
        "current-key"
    ]
    db.close()


def test_mark_stale_jobs_failed_recovers_lost_worker_tasks(session_factory):
    db = session_factory()
    stale = IngestJob(
        kind="crawl",
        status="running",
        updated_at="2026-10-20T00:00:00+00:00",
    )
    current = IngestJob(
        kind="upload",
        status="queued",
        updated_at="2026-10-24T00:00:00+00:00",
    )
    db.add_all([stale, current])
    db.commit()

    changed = mark_stale_jobs_failed(
        db,
        before="2026-10-23T00:00:00+00:00",
    )

    assert changed == 1
    assert stale.status == "failed"
    assert stale.progress == 100
    assert current.status == "queued"
    db.close()
