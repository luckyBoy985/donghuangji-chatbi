from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.core.limits import (
    MemoryDailyQuota,
    RedisDailyQuota,
    get_daily_quota,
)
from backend.app.core.security import AdminUser
from backend.app.models.entities import utc_now
from backend.app.models.ingestion import (
    DataChunk,
    DataDocument,
    DataSource,
    IngestJob,
)
from backend.app.schemas.data_admin import (
    CrawlerRunRequest,
    DataDocumentDetail,
    DataDocumentOut,
    DataDocumentPage,
    DataDocumentUpdate,
    DataOverviewOut,
    DataSourceOut,
    IngestJobOut,
)
from backend.app.services.audit.service import record_audit
from backend.app.services.ingestion.parsers import (
    validate_file_signature,
    validate_upload,
)
from backend.app.services.ingestion.service import ensure_crawler_sources
from backend.app.services.storage import put_bytes

router = APIRouter(prefix="/api/admin/data", tags=["data-admin"])


def _job_out(job: IngestJob) -> IngestJobOut:
    try:
        stats = json.loads(job.stats_json or "{}")
    except json.JSONDecodeError:
        stats = {}
    return IngestJobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        product=job.product,
        section=job.section,
        title=job.title,
        original_name=job.original_name,
        object_key=job.object_key,
        source_id=job.source_id,
        progress=job.progress,
        message=job.message,
        stats=stats,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _store_upload(key: str, content: bytes, content_type: str) -> str:
    return put_bytes(key, content, content_type)


def _enqueue_job(job_id: str) -> None:
    from backend.app.core.workers import run_ingest_job

    run_ingest_job.delay(job_id)


def _safe_filename(filename: str) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix.lower()
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", stem).strip("._")
    return (cleaned[:120] or "upload") + suffix


def _document_out(
    document: DataDocument,
    chunk_count: int = 0,
) -> DataDocumentOut:
    return DataDocumentOut(
        doc_id=document.doc_id,
        product=document.product,
        source_type=document.source_type,
        section=document.section,
        title=document.title,
        published_at=document.published_at,
        url=document.url,
        original_name=document.original_name,
        content_hash=document.content_hash,
        chars=document.chars,
        status=document.status,
        origin=document.origin,
        source_id=document.source_id,
        chunk_count=chunk_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _create_job(
    db: Session,
    *,
    kind: str,
    admin_id: str,
    product: str = "",
    section: str = "",
    source_id: str | None = None,
) -> IngestJob:
    job = IngestJob(
        kind=kind,
        product=product,
        section=section,
        source_id=source_id,
        created_by=admin_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/uploads", response_model=IngestJobOut, status_code=202)
async def upload_document(
    admin: AdminUser,
    file: UploadFile = File(...),
    product: str = Form(...),
    section: str = Form(default="产品资料"),
    title: str = Form(default=""),
    db: Session = Depends(get_db),
    quota: MemoryDailyQuota | RedisDailyQuota = Depends(get_daily_quota),
) -> IngestJobOut:
    filename = Path(file.filename or "upload").name
    content = await file.read()
    try:
        suffix = validate_upload(filename, len(content))
        validate_file_signature(filename, content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    product = product.strip()
    section = section.strip()
    if not product or len(product) > 80:
        raise HTTPException(status_code=422, detail="产品名称无效")
    if len(section) > 160:
        raise HTTPException(status_code=422, detail="栏目名称过长")
    if not quota.consume(
        f"admin-data:{admin.id}",
        limit=settings.admin_data_daily_limit,
    ):
        raise HTTPException(status_code=429, detail="今日数据操作额度已用完")

    job = IngestJob(
        kind="upload",
        product=product,
        section=section or "产品资料",
        title=(title.strip() or Path(filename).stem)[:300],
        original_name=filename[:300],
        created_by=admin.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    key = f"uploads/{job.id}/{_safe_filename(filename)}"
    try:
        key = _store_upload(
            key,
            content,
            file.content_type or f"application/{suffix.lstrip('.')}",
        )
    except Exception as error:
        job.status = "failed"
        job.error = f"对象存储写入失败：{type(error).__name__}"
        job.message = "上传失败"
        job.progress = 100
        job.finished_at = utc_now()
        job.updated_at = utc_now()
        db.commit()
        raise HTTPException(status_code=503, detail="对象存储暂不可用") from error

    job.object_key = key
    job.updated_at = utc_now()
    record_audit(
        db,
        actor_user_id=admin.id,
        action="data.upload",
        resource_type="ingest_job",
        resource_id=job.id,
        metadata={"product": job.product, "section": job.section},
    )
    db.commit()
    db.refresh(job)
    _enqueue_job(job.id)
    return _job_out(job)


@router.get("/overview", response_model=DataOverviewOut)
def data_overview(
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> DataOverviewOut:
    documents = db.scalar(select(func.count()).select_from(DataDocument)) or 0
    active = (
        db.scalar(
            select(func.count())
            .select_from(DataDocument)
            .where(DataDocument.status == "active")
        )
        or 0
    )
    chunks = (
        db.scalar(
            select(func.count())
            .select_from(DataChunk)
            .join(DataDocument, DataDocument.doc_id == DataChunk.doc_id)
            .where(DataDocument.status == "active")
        )
        or 0
    )
    product_rows = db.execute(
        select(
            DataDocument.product,
            func.count(DataDocument.doc_id),
            func.sum(DataDocument.chars),
        )
        .where(DataDocument.status == "active")
        .group_by(DataDocument.product)
        .order_by(func.count(DataDocument.doc_id).desc())
    ).all()
    jobs = db.scalars(
        select(IngestJob).order_by(IngestJob.created_at.desc()).limit(8)
    ).all()
    return DataOverviewOut(
        documents=documents,
        active_documents=active,
        archived_documents=documents - active,
        chunks=chunks,
        products=[
            {
                "product": product,
                "documents": document_count,
                "chars": chars or 0,
            }
            for product, document_count, chars in product_rows
        ],
        recent_jobs=[_job_out(job) for job in jobs],
    )


@router.get("/documents", response_model=DataDocumentPage)
def list_documents(
    _admin: AdminUser,
    q: str = "",
    product: str = "",
    section: str = "",
    status: str = Query(default="", pattern=r"^(active|archived)?$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> DataDocumentPage:
    counts = (
        select(
            DataChunk.doc_id,
            func.count(DataChunk.chunk_id).label("chunk_count"),
        )
        .group_by(DataChunk.doc_id)
        .subquery()
    )
    filters = []
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                DataDocument.title.ilike(pattern),
                DataDocument.original_name.ilike(pattern),
                DataDocument.doc_id.ilike(pattern),
            )
        )
    if product.strip():
        filters.append(DataDocument.product == product.strip())
    if section.strip():
        filters.append(DataDocument.section == section.strip())
    if status:
        filters.append(DataDocument.status == status)

    total = (
        db.scalar(
            select(func.count())
            .select_from(DataDocument)
            .where(*filters)
        )
        or 0
    )
    statement = (
        select(DataDocument, func.coalesce(counts.c.chunk_count, 0))
        .outerjoin(counts, counts.c.doc_id == DataDocument.doc_id)
        .where(*filters)
        .order_by(DataDocument.updated_at.desc(), DataDocument.title)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.execute(statement).all()
    return DataDocumentPage(
        items=[
            _document_out(document, int(chunk_count))
            for document, chunk_count in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{doc_id}", response_model=DataDocumentDetail)
def document_detail(
    doc_id: str,
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> DataDocumentDetail:
    document = db.get(DataDocument, doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    chunks = list(
        db.scalars(
            select(DataChunk)
            .where(DataChunk.doc_id == doc_id)
            .order_by(DataChunk.ordinal)
        ).all()
    )
    return DataDocumentDetail(
        **_document_out(document, len(chunks)).model_dump(),
        content="\n\n".join(chunk.text for chunk in chunks),
    )


@router.patch("/documents/{doc_id}", response_model=DataDocumentOut)
def update_document(
    doc_id: str,
    payload: DataDocumentUpdate,
    admin: AdminUser,
    db: Session = Depends(get_db),
    quota: MemoryDailyQuota | RedisDailyQuota = Depends(get_daily_quota),
) -> DataDocumentOut:
    document = db.get(DataDocument, doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not quota.consume(
        f"admin-data:{admin.id}",
        limit=settings.admin_data_daily_limit,
    ):
        raise HTTPException(status_code=429, detail="今日数据操作额度已用完")
    if payload.title is not None:
        document.title = payload.title.strip()
    if payload.section is not None:
        document.section = payload.section.strip()
    if payload.status is not None:
        document.status = payload.status
    document.updated_at = utc_now()
    record_audit(
        db,
        actor_user_id=admin.id,
        action="data.document_update",
        resource_type="data_document",
        resource_id=doc_id,
        metadata=payload.model_dump(exclude_none=True),
    )
    db.commit()
    job = _create_job(
        db,
        kind="reindex",
        admin_id=admin.id,
        product=document.product,
    )
    _enqueue_job(job.id)
    count = (
        db.scalar(
            select(func.count())
            .select_from(DataChunk)
            .where(DataChunk.doc_id == doc_id)
        )
        or 0
    )
    return _document_out(document, count)


@router.get("/jobs", response_model=list[IngestJobOut])
def list_jobs(
    _admin: AdminUser,
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[IngestJobOut]:
    rows = db.scalars(
        select(IngestJob)
        .order_by(IngestJob.created_at.desc())
        .limit(limit)
    ).all()
    return [_job_out(job) for job in rows]


@router.get("/jobs/{job_id}", response_model=IngestJobOut)
def get_job(
    job_id: str,
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> IngestJobOut:
    job = db.get(IngestJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _job_out(job)


@router.get("/sources", response_model=list[DataSourceOut])
def list_sources(
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> list[DataSourceOut]:
    sources = ensure_crawler_sources(db, created_by=admin.id)
    active_jobs = {
        job.source_id: job.id
        for job in db.scalars(
            select(IngestJob).where(IngestJob.status.in_(["queued", "running"]))
        ).all()
        if job.source_id
    }
    return [
        DataSourceOut(
            id=source.id,
            name=source.name,
            kind=source.kind,
            crawler_key=source.crawler_key,
            product=source.product,
            status=source.status,
            last_run_at=source.last_run_at,
            active_job_id=active_jobs.get(source.id),
        )
        for source in sources
    ]


@router.post(
    "/sources/{source_id}/run",
    response_model=IngestJobOut,
    status_code=202,
)
def run_crawler_source(
    source_id: str,
    payload: CrawlerRunRequest,
    admin: AdminUser,
    db: Session = Depends(get_db),
    quota: MemoryDailyQuota | RedisDailyQuota = Depends(get_daily_quota),
) -> IngestJobOut:
    if not quota.consume(
        f"admin-data:{admin.id}",
        limit=settings.admin_data_daily_limit,
    ):
        raise HTTPException(status_code=429, detail="今日数据操作额度已用完")
    ensure_crawler_sources(db, created_by=admin.id)
    source = db.get(DataSource, source_id)
    if source is None or source.kind != "crawler" or source.status != "active":
        raise HTTPException(status_code=404, detail="数据源不存在")
    active = db.scalar(
        select(IngestJob.id).where(
            IngestJob.source_id == source.id,
            IngestJob.status.in_(["queued", "running"]),
        )
    )
    if active:
        raise HTTPException(status_code=409, detail="该数据源已有任务正在执行")
    try:
        config = json.loads(source.config_json or "{}")
    except json.JSONDecodeError:
        config = {}
    config["last_max_pages"] = payload.max_pages
    source.config_json = json.dumps(config, ensure_ascii=False)
    source.updated_at = utc_now()
    db.commit()
    job = _create_job(
        db,
        kind="crawl",
        admin_id=admin.id,
        product=source.product,
        source_id=source.id,
    )
    record_audit(
        db,
        actor_user_id=admin.id,
        action="data.crawler_run",
        resource_type="data_source",
        resource_id=source.id,
        metadata={"max_pages": payload.max_pages},
    )
    db.commit()
    _enqueue_job(job.id)
    return _job_out(job)


@router.post("/index/rebuild", response_model=IngestJobOut, status_code=202)
def rebuild_index_now(
    admin: AdminUser,
    db: Session = Depends(get_db),
    quota: MemoryDailyQuota | RedisDailyQuota = Depends(get_daily_quota),
) -> IngestJobOut:
    if not quota.consume(
        f"admin-data:{admin.id}",
        limit=settings.admin_data_daily_limit,
    ):
        raise HTTPException(status_code=429, detail="今日数据操作额度已用完")
    job = _create_job(db, kind="reindex", admin_id=admin.id)
    record_audit(
        db,
        actor_user_id=admin.id,
        action="data.index_rebuild",
        resource_type="ingest_job",
        resource_id=job.id,
    )
    db.commit()
    _enqueue_job(job.id)
    return _job_out(job)
