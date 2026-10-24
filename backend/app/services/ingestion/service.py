from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models.entities import utc_now
from backend.app.models.ingestion import (
    DataChunk,
    DataDocument,
    DataSource,
    IngestJob,
)
from backend.app.services.data.embedder import get_embedder
from backend.app.services.ingestion.crawlers import (
    CRAWLERS,
    CrawlDocument,
    crawl,
    crawl_snapshot_key,
)
from backend.app.services.ingestion.indexer import rebuild_platform_index
from backend.app.services.ingestion.parsers import (
    ParsedDocument,
    chunk_markdown,
    parse_upload,
)
from backend.app.services.storage import get_bytes, put_bytes


@dataclass(slots=True)
class IngestDocument:
    doc_id: str
    product: str
    source_type: str
    section: str
    title: str
    url: str
    published_at: str
    body: str
    content_hash: str
    original_name: str
    object_key: str


class TransientIngestError(OSError):
    pass


def upsert_document(
    db: Session,
    document: IngestDocument,
    *,
    origin: str,
    source_id: str | None = None,
    created_by: str | None = None,
) -> dict:
    now = utc_now()
    row = db.get(DataDocument, document.doc_id)
    chunks = chunk_markdown(document.body)
    if not chunks:
        raise ValueError("正文无法切分为检索块")
    inserted = row is None
    reactivated = row is not None and row.status != "active"
    expected_chunks = [
        (f"{document.doc_id}::{index:03d}", text)
        for index, text in enumerate(chunks)
    ]
    existing_chunks = (
        []
        if row is None
        else [
            (chunk.chunk_id, chunk.text)
            for chunk in db.scalars(
                select(DataChunk)
                .where(DataChunk.doc_id == document.doc_id)
                .order_by(DataChunk.ordinal)
            ).all()
        ]
    )
    changed = (
        inserted
        or reactivated
        or row.content_hash != document.content_hash
        or existing_chunks != expected_chunks
    )
    if row is None:
        row = DataDocument(
            doc_id=document.doc_id,
            content_hash=document.content_hash,
            created_at=now,
            created_by=created_by,
        )
        db.add(row)
    row.product = document.product
    row.source_type = document.source_type
    row.section = document.section[:160]
    row.title = document.title[:300]
    row.published_at = document.published_at[:40]
    row.url = document.url
    row.original_name = document.original_name[:300]
    row.object_key = document.object_key[:1024]
    row.content_hash = document.content_hash
    row.chars = len(document.body)
    row.status = "active"
    row.origin = origin
    row.source_id = source_id
    row.updated_at = now
    if created_by:
        row.created_by = created_by
    if changed:
        db.execute(delete(DataChunk).where(DataChunk.doc_id == document.doc_id))
        for ordinal, (chunk_id, text) in enumerate(expected_chunks):
            db.add(
                DataChunk(
                    chunk_id=chunk_id,
                    doc_id=document.doc_id,
                    ordinal=ordinal,
                    text=text,
                )
            )
    return {
        "doc_id": document.doc_id,
        "inserted": inserted,
        "changed": changed,
        "chunks": len(chunks),
    }


def normalized_upload(parsed: ParsedDocument, object_key: str) -> IngestDocument:
    return IngestDocument(
        doc_id=parsed.doc_id,
        product=parsed.product,
        source_type="internal",
        section=parsed.section,
        title=parsed.title,
        url="",
        published_at="",
        body=parsed.body,
        content_hash=parsed.content_hash,
        original_name=parsed.original_name,
        object_key=object_key,
    )


def normalized_crawl(
    document: CrawlDocument,
    object_key: str = "",
) -> IngestDocument:
    return IngestDocument(
        doc_id=document.doc_id,
        product=document.product,
        source_type=document.source_type,
        section=document.section,
        title=document.title,
        url=document.url,
        published_at=document.published_at,
        body=document.body,
        content_hash=document.content_hash,
        original_name="",
        object_key=object_key,
    )


def ensure_crawler_sources(
    db: Session,
    *,
    created_by: str | None = None,
) -> list[DataSource]:
    rows: list[DataSource] = []
    for key, spec in CRAWLERS.items():
        source = db.get(DataSource, f"crawler_{key}")
        if source is None:
            source = DataSource(
                id=f"crawler_{key}",
                name=spec.name,
                kind="crawler",
                crawler_key=key,
                product=spec.product,
                config_json=json.dumps(
                    {"official_site": spec.official_site},
                    ensure_ascii=False,
                ),
                created_by=created_by,
            )
            db.add(source)
        elif source.status != "active":
            source.status = "active"
        rows.append(source)
    db.commit()
    return rows


def archive_missing_documents(
    db: Session,
    *,
    source_id: str,
    seen_doc_ids: set[str],
) -> int:
    rows = list(
        db.scalars(
            select(DataDocument).where(
                DataDocument.source_id == source_id,
                DataDocument.status == "active",
            )
        ).all()
    )
    if not seen_doc_ids or len(seen_doc_ids) < len(rows) * 0.8:
        return 0
    archived = 0
    now = utc_now()
    for row in rows:
        if row.doc_id not in seen_doc_ids:
            row.status = "archived"
            row.updated_at = now
            archived += 1
    return archived


def rebuild_index(db: Session) -> dict:
    source = (
        settings.platform_index_path
        if settings.platform_index_path.exists()
        else settings.index_path
    )
    result = rebuild_platform_index(
        db,
        source_index=source,
        output_path=settings.platform_index_path,
        embedder=get_embedder(),
        manifest_path=settings.platform_manifest_path,
        model_id=f"{settings.bge_m3_path.name}:{settings.embedding_dim}",
    )
    return {
        "chunks": result.chunks,
        "embedded": result.embedded,
        "reused": result.reused,
    }


def _update_job(
    db: Session,
    job: IngestJob,
    *,
    status: str,
    progress: int,
    message: str,
    stats: dict | None = None,
) -> None:
    now = utc_now()
    job.status = status
    job.progress = progress
    job.message = message[:500]
    job.updated_at = now
    if status == "running" and job.started_at is None:
        job.started_at = now
    if status in {"completed", "failed"}:
        job.finished_at = now
    if stats is not None:
        job.stats_json = json.dumps(stats, ensure_ascii=False)
    db.commit()


def process_upload(db: Session, job: IngestJob) -> dict:
    _update_job(
        db,
        job,
        status="running",
        progress=10,
        message="正在读取上传文件",
    )
    try:
        content = get_bytes(job.object_key)
    except (OSError, TimeoutError) as error:
        raise TransientIngestError("对象存储暂时不可用") from error
    parsed = parse_upload(
        content,
        filename=job.original_name,
        product=job.product,
        section=job.section,
        title=job.title,
    )
    _update_job(
        db,
        job,
        status="running",
        progress=45,
        message="正在解析并写入文档",
    )
    result = upsert_document(
        db,
        normalized_upload(parsed, job.object_key),
        origin="upload",
        created_by=job.created_by,
    )
    db.commit()
    _update_job(
        db,
        job,
        status="running",
        progress=70,
        message="正在更新检索索引",
    )
    index = rebuild_index(db)
    stats = {**result, "index": index}
    _update_job(
        db,
        job,
        status="completed",
        progress=100,
        message="上传资料已加入知识库",
        stats=stats,
    )
    return stats


def process_crawl(db: Session, job: IngestJob) -> dict:
    source = db.get(DataSource, job.source_id) if job.source_id else None
    if source is None or not source.crawler_key:
        raise ValueError("数据源不存在")
    _update_job(
        db,
        job,
        status="running",
        progress=5,
        message=f"正在抓取{source.name}",
    )
    max_pages = int(
        json.loads(source.config_json or "{}").get("last_max_pages", 60)
    )
    documents = crawl(source.crawler_key, max_pages)
    if not documents:
        raise TransientIngestError(
            "本次抓取未获得任何正文，已保留原有资料"
        )
    _update_job(
        db,
        job,
        status="running",
        progress=55,
        message=f"已抓取 {len(documents)} 篇，正在增量入库",
    )
    seen: set[str] = set()
    inserted = changed = unchanged = chunks = 0
    existing_active = (
        db.scalar(
            select(func.count())
            .select_from(DataDocument)
            .where(
                DataDocument.source_id == source.id,
                DataDocument.status == "active",
            )
        )
        or 0
    )
    for item in documents:
        snapshot_key = crawl_snapshot_key(
            source.id,
            item.content_hash,
            item.doc_id,
            item.raw_extension,
        )
        raw_content = item.raw_content or item.body
        content_type = {
            "html": "text/html; charset=utf-8",
            "json": "application/json",
            "txt": "text/plain; charset=utf-8",
        }[item.raw_extension if item.raw_extension in {"html", "json", "txt"} else "txt"]
        try:
            put_bytes(
                snapshot_key,
                raw_content.encode("utf-8"),
                content_type,
            )
        except (OSError, TimeoutError) as error:
            raise TransientIngestError("抓取快照写入失败") from error
        result = upsert_document(
            db,
            normalized_crawl(item, snapshot_key),
            origin="crawler",
            source_id=source.id,
        )
        seen.add(item.doc_id)
        inserted += int(result["inserted"])
        changed += int(result["changed"])
        unchanged += int(not result["changed"])
        chunks += result["chunks"]
    db.commit()
    archived = archive_missing_documents(
        db,
        source_id=source.id,
        seen_doc_ids=seen,
    )
    coverage_guard_triggered = bool(
        existing_active
        and len(seen) < existing_active * 0.8
    )
    source.last_run_at = utc_now()
    source.updated_at = source.last_run_at
    db.commit()
    _update_job(
        db,
        job,
        status="running",
        progress=75,
        message="正在重建混合检索索引",
    )
    index = rebuild_index(db)
    stats = {
        "documents": len(documents),
        "inserted": inserted,
        "changed": changed,
        "unchanged": unchanged,
        "archived": archived,
        "snapshot_count": len(documents),
        "coverage_guard_triggered": coverage_guard_triggered,
        "chunks": chunks,
        "index": index,
    }
    _update_job(
        db,
        job,
        status="completed",
        progress=100,
        message=(
            "增量重抓完成（抓取覆盖不足，已跳过下架判定）"
            if coverage_guard_triggered
            else "增量重抓完成"
        ),
        stats=stats,
    )
    return stats
