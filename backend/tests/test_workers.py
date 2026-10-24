import subprocess
import sys
from pathlib import Path

from backend.app.models.ingestion import IngestJob
from backend.app.services.ingestion import service
from backend.app.core.workers import execute_ingest_job
from backend.app.core.workers import celery_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_worker_marks_job_failed_when_storage_read_fails(
    session_factory, monkeypatch
):
    db = session_factory()
    job = IngestJob(
        kind="upload",
        product="东煌纪",
        section="产品资料",
        title="失败任务",
        original_name="失败.md",
        object_key="uploads/missing.md",
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    def fail_read(_key):
        raise OSError("storage unavailable")

    monkeypatch.setattr(service, "get_bytes", fail_read)

    try:
        execute_ingest_job(job_id, session_factory=session_factory)
    except OSError:
        pass
    else:
        raise AssertionError("worker should surface the original failure")

    db = session_factory()
    failed = db.get(IngestJob, job_id)
    assert failed.status == "failed"
    assert failed.progress == 100
    assert "TransientIngestError" in failed.error
    assert failed.finished_at is not None
    db.close()


def test_fresh_worker_process_registers_foreign_key_tables():
    script = """
from sqlalchemy import create_engine
from backend.app.core import workers
from backend.app.models.ingestion import IngestJob
from backend.app.models.base import Base
Base.metadata.create_all(create_engine("sqlite:///:memory:"))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr


def test_celery_has_time_limits_and_maintenance_schedule():
    assert celery_app.conf.task_soft_time_limit > 0
    assert celery_app.conf.task_time_limit > celery_app.conf.task_soft_time_limit
    assert celery_app.conf.beat_schedule["maintenance-hourly"]["task"] == (
        "maintenance.cleanup"
    )
