import json
from datetime import timedelta

from celery import Celery
from botocore.exceptions import BotoCoreError

from backend.app.core.config import settings
from backend.app.services.ingestion.service import TransientIngestError

celery_app = Celery("chatbi", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.ingest_soft_time_limit,
    task_time_limit=settings.ingest_time_limit,
    beat_schedule={
        "maintenance-hourly": {
            "task": "maintenance.cleanup",
            "schedule": timedelta(hours=1),
        },
    },
)


@celery_app.task(name="health.ping")
def health_ping() -> str:
    return "pong"


def execute_ingest_job(job_id: str, *, session_factory=None) -> dict:
    from backend.app.core.database import SessionLocal
    from backend.app.models.entities import utc_now
    from backend.app.models.ingestion import IngestJob
    from backend.app.services.ingestion.service import (
        process_crawl,
        process_upload,
        rebuild_index,
    )

    factory = session_factory or SessionLocal
    db = factory()
    try:
        job = db.get(IngestJob, job_id)
        if job is None:
            raise ValueError("数据任务不存在")
        try:
            if job.kind == "upload":
                return process_upload(db, job)
            if job.kind == "crawl":
                return process_crawl(db, job)
            if job.kind == "reindex":
                now = utc_now()
                job.status = "running"
                job.progress = 10
                job.message = "正在重建检索索引"
                job.started_at = job.started_at or now
                job.updated_at = now
                db.commit()
                stats = rebuild_index(db)
                job.status = "completed"
                job.progress = 100
                job.message = "检索索引重建完成"
                job.stats_json = json.dumps(stats, ensure_ascii=False)
                job.finished_at = utc_now()
                job.updated_at = job.finished_at
                db.commit()
                return stats
            raise ValueError("不支持的数据任务类型")
        except Exception as error:
            db.rollback()
            failed = db.get(IngestJob, job_id)
            if failed is not None:
                failed.status = "failed"
                failed.progress = 100
                failed.message = "任务失败"
                failed.error = f"{type(error).__name__}: {str(error)[:800]}"
                failed.finished_at = utc_now()
                failed.updated_at = failed.finished_at
                db.commit()
            raise
    finally:
        db.close()


@celery_app.task(
    name="data.ingest",
    soft_time_limit=settings.ingest_soft_time_limit,
    time_limit=settings.ingest_time_limit,
    autoretry_for=(TransientIngestError, OSError, TimeoutError, BotoCoreError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def run_ingest_job(job_id: str) -> dict:
    return execute_ingest_job(job_id)


@celery_app.task(name="maintenance.cleanup")
def run_maintenance() -> dict:
    from backend.app.core.database import SessionLocal
    from backend.app.services.maintenance import run_scheduled_maintenance

    db = SessionLocal()
    try:
        return run_scheduled_maintenance(db)
    finally:
        db.close()
