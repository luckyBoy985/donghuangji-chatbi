from __future__ import annotations

import argparse
import hashlib
import pickle
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.models.ingestion import DataChunk, DataDocument


def seed_index_documents(
    db: Session,
    *,
    index_path: Path,
) -> dict[str, int]:
    if not index_path.exists():
        raise FileNotFoundError(f"索引不存在：{index_path}")
    with index_path.open("rb") as handle:
        payload = pickle.load(handle)
    chunks = list(payload.get("chunks") or [])
    grouped: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        grouped[str(chunk.get("doc_id", ""))].append(chunk)

    for doc_id, doc_chunks in grouped.items():
        if not doc_id:
            continue
        doc_chunks.sort(key=lambda item: str(item.get("chunk_id", "")))
        first = doc_chunks[0]
        body = "\n\n".join(str(item.get("text", "")) for item in doc_chunks)
        document = db.get(DataDocument, doc_id)
        if document is not None:
            continue
        db.add(
            DataDocument(
                doc_id=doc_id,
                product=str(first.get("product", "")),
                source_type=str(first.get("source_type", "")),
                section=str(first.get("section", "")),
                title=str(first.get("title", "")),
                published_at=str(first.get("published_at", "")),
                url=str(first.get("url", "")),
                content_hash=hashlib.sha256(
                    body.encode("utf-8")
                ).hexdigest(),
                chars=len(body),
                status="active",
                origin="baseline",
            )
        )
        for ordinal, chunk in enumerate(doc_chunks):
            chunk_id = str(chunk.get("chunk_id", ""))
            if not chunk_id or db.get(DataChunk, chunk_id) is not None:
                continue
            db.add(
                DataChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    ordinal=ordinal,
                    text=str(chunk.get("text", "")),
                    content_hash=hashlib.sha256(
                        str(chunk.get("text", "")).encode("utf-8")
                    ).hexdigest(),
                )
            )
    db.commit()
    return {"documents": len(grouped), "chunks": len(chunks)}


def main() -> None:
    parser = argparse.ArgumentParser(description="同步基线索引到数据管理表")
    parser.add_argument("--index", type=Path, default=None)
    args = parser.parse_args()
    from backend.app.core.config import settings
    from backend.app.core.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        result = seed_index_documents(
            db,
            index_path=args.index or settings.index_path,
        )
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
