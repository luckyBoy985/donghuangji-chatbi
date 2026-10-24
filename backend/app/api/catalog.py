import json
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import CurrentUser
from backend.app.models.ingestion import DataChunk, DataDocument

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/catalog")
def get_catalog(
    _user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    total_document_count = (
        db.scalar(
            select(func.count())
            .select_from(DataDocument)
        )
        or 0
    )
    if total_document_count:
        document_count = (
            db.scalar(
                select(func.count())
                .select_from(DataDocument)
                .where(DataDocument.status == "active")
            )
            or 0
        )
        product_rows = db.execute(
            select(
                DataDocument.product,
                func.count(func.distinct(DataDocument.doc_id)),
                func.count(DataChunk.chunk_id),
            )
            .outerjoin(DataChunk, DataChunk.doc_id == DataDocument.doc_id)
            .where(DataDocument.status == "active")
            .group_by(DataDocument.product)
        ).all()
        section_rows = db.execute(
            select(DataDocument.product, DataDocument.section)
            .where(DataDocument.status == "active")
            .distinct()
        ).all()
        sections: dict[str, set[str]] = defaultdict(set)
        for product, section in section_rows:
            if section:
                sections[product].add(section)
        products = [
            {
                "name": product,
                "documents": documents,
                "chunks": chunks,
                "sections": sorted(sections[product]),
            }
            for product, documents, chunks in sorted(
                product_rows,
                key=lambda row: (-row[2], row[0]),
            )
        ]
        return {
            "documents": document_count,
            "chunks": sum(int(product["chunks"]) for product in products),
            "embedding_dim": settings.embedding_dim,
            "products": products,
        }
    if not settings.catalog_path.exists():
        raise HTTPException(status_code=503, detail="数据目录尚未导入")
    return json.loads(settings.catalog_path.read_text(encoding="utf-8"))
