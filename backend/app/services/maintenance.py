from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models.audit import AuditLog
from backend.app.models.entities import utc_now
from backend.app.models.identity import LoginAttempt
from backend.app.models.ingestion import IngestJob


def cleanup_audit_logs(db: Session, *, before: str) -> int:
    result = db.execute(delete(AuditLog).where(AuditLog.created_at < before))
    db.commit()
    return int(result.rowcount or 0)


def cleanup_login_attempts(db: Session, *, before: str) -> int:
    result = db.execute(
        delete(LoginAttempt).where(LoginAttempt.failed_at < before)
    )
    db.commit()
    return int(result.rowcount or 0)


def mark_stale_jobs_failed(db: Session, *, before: str) -> int:
    now = utc_now()
    result = db.execute(
        update(IngestJob)
        .where(
            IngestJob.status.in_(["queued", "running"]),
            IngestJob.updated_at < before,
        )
        .values(
            status="failed",
            progress=100,
            message="任务超时或 Worker 中断",
            error="stale job recovered by maintenance task",
            finished_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session="fetch")
    )
    db.commit()
    return int(result.rowcount or 0)


def run_scheduled_maintenance(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    audit_before = (
        current - timedelta(days=settings.audit_retention_days)
    ).isoformat()
    attempt_before = (
        current
        - timedelta(seconds=max(settings.login_window_seconds * 2, 3600))
    ).isoformat()
    jobs_before = (
        current - timedelta(hours=settings.stale_job_hours)
    ).isoformat()
    return {
        "audit_logs": cleanup_audit_logs(db, before=audit_before),
        "login_attempts": cleanup_login_attempts(db, before=attempt_before),
        "stale_jobs": mark_stale_jobs_failed(db, before=jobs_before),
    }
