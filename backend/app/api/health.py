import pickle

import numpy as np
from fastapi import APIRouter, Depends
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.models.ingestion import DataChunk, DataDocument
from backend.app.services.data.index_manifest import (
    database_fingerprint,
    validate_index_manifest,
)
from backend.app.services.data.embedder import get_embedder
from backend.app.services.data.reranker import get_reranker
from backend.app.services.storage import get_s3_client

router = APIRouter(prefix="/api", tags=["health"])


def _path_status(path) -> dict:
    return {"status": "ready" if path.exists() else "unavailable"}


def _redis_status() -> dict:
    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
    )
    try:
        return {"status": "ready" if client.ping() else "unavailable"}
    except RedisError:
        return {"status": "unavailable"}
    finally:
        client.close()


def _minio_status() -> dict:
    try:
        get_s3_client().head_bucket(Bucket=settings.s3_bucket)
        return {"status": "ready", "bucket": settings.s3_bucket}
    except Exception:
        return {"status": "unavailable", "bucket": settings.s3_bucket}


def _index_status(db: Session) -> dict:
    platform = settings.platform_index_path
    path = platform if platform.exists() else settings.index_path
    if not path.exists():
        return {"status": "unavailable", "path": str(path)}
    manifest: dict = {}
    manifest_status = "not-applicable"
    if path == platform:
        try:
            manifest = validate_index_manifest(
                path,
                settings.platform_manifest_path,
            )
            manifest_status = "verified" if manifest else "missing"
        except ValueError:
            return {
                "status": "unavailable",
                "path": str(path),
                "manifest_status": "invalid",
                "manifest_path": str(settings.platform_manifest_path),
            }
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    chunks = list(payload.get("chunks") or [])
    dense = np.asarray(payload.get("dense"))
    document_count = len({chunk.get("doc_id") for chunk in chunks})
    db_documents = (
        db.scalar(
            select(func.count())
            .select_from(DataDocument)
            .where(DataDocument.status == "active")
        )
        or 0
    )
    db_rows = db.execute(
        select(DataChunk, DataDocument)
        .join(DataDocument, DataDocument.doc_id == DataChunk.doc_id)
        .where(DataDocument.status == "active")
        .order_by(
            DataDocument.product,
            DataDocument.title,
            DataChunk.doc_id,
            DataChunk.ordinal,
        )
    ).all()
    db_chunks = [
        {
            "chunk_id": chunk.chunk_id,
            "doc_id": document.doc_id,
            "product": document.product,
            "section": document.section,
            "title": document.title,
            "text": chunk.text,
        }
        for chunk, document in db_rows
    ]
    fingerprint = database_fingerprint(db_chunks)
    counts_match = (
        db_documents == 0
        or (
            db_documents == document_count
            and len(db_chunks) == len(chunks)
            and (
                not manifest
                or manifest.get("database_fingerprint") == fingerprint
            )
        )
    )
    if manifest_status == "missing":
        status = "legacy"
    elif counts_match:
        status = "ready"
    else:
        status = "degraded"
    return {
        "status": status,
        "path": str(path),
        "manifest_status": manifest_status,
        "generation": manifest.get("generation"),
        "model_id": manifest.get("model_id"),
        "documents": document_count,
        "chunks": len(chunks),
        "embedding_dim": int(dense.shape[1]) if dense.ndim == 2 else None,
        "database": {
            "documents": db_documents,
            "chunks": len(db_chunks),
            "fingerprint_match": bool(
                manifest
                and manifest.get("database_fingerprint") == fingerprint
            ),
        },
    }


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    index = _index_status(db)
    redis = _redis_status()
    minio = _minio_status()
    healthy = (
        index["status"] == "ready"
        and redis["status"] == "ready"
        and minio["status"] == "ready"
    )
    return {
        "status": "ok" if healthy else "degraded",
        "index": index,
        "bge": {
            **_path_status(settings.bge_m3_path),
            "model_loaded": get_embedder().loaded,
        },
        "reranker": {
            **_path_status(settings.bge_reranker_path),
            "model_loaded": get_reranker().loaded,
        },
        "redis": redis,
        "minio": minio,
        "llm": {
            "status": "ready"
            if settings.deepseek_api_key.strip()
            else "degraded",
            "model": settings.llm_model,
        },
    }
