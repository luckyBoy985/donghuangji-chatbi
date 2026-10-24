from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import pickle
from typing import Protocol

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.ingestion import DataChunk, DataDocument
from backend.app.services.data.index_manifest import write_index_manifest


class DocumentEmbedder(Protocol):
    def encode_documents(self, texts: list[str]) -> np.ndarray: ...


@dataclass(slots=True)
class IndexResult:
    chunks: int
    embedded: int
    reused: int


def rebuild_platform_index(
    db: Session,
    *,
    source_index: Path,
    output_path: Path,
    embedder: DocumentEmbedder,
    manifest_path: Path | None = None,
    model_id: str = "bge-m3",
) -> IndexResult:
    source_chunks: list[dict] = []
    source_dense = np.empty((0, 0), dtype=np.float32)
    if source_index.exists():
        with source_index.open("rb") as handle:
            source = pickle.load(handle)
        source_chunks = list(source.get("chunks") or [])
        source_dense = np.asarray(source.get("dense"), dtype=np.float32)
        if source_dense.ndim != 2 or source_dense.shape[0] != len(source_chunks):
            raise ValueError("基础索引格式无效")

    source_by_id = {
        str(chunk.get("chunk_id")): (chunk, source_dense[index])
        for index, chunk in enumerate(source_chunks)
    }
    rows = db.execute(
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

    chunks: list[dict] = []
    vectors: list[np.ndarray | None] = []
    pending_texts: list[str] = []
    pending_positions: list[int] = []
    for chunk, document in rows:
        chunks.append(
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": document.doc_id,
                "product": document.product,
                "source_type": document.source_type,
                "section": document.section,
                "title": document.title,
                "url": document.url,
                "published_at": document.published_at,
                "text": chunk.text,
            }
        )
        cached = source_by_id.get(chunk.chunk_id)
        if cached and str(cached[0].get("text", "")) == chunk.text:
            vectors.append(np.asarray(cached[1], dtype=np.float32))
        else:
            vectors.append(None)
            pending_texts.append(chunk.text)
            pending_positions.append(len(vectors) - 1)

    embedded = 0
    if pending_texts:
        generated = np.asarray(
            embedder.encode_documents(pending_texts),
            dtype=np.float32,
        )
        if generated.ndim != 2 or generated.shape[0] != len(pending_texts):
            raise ValueError("嵌入模型返回维度无效")
        for position, vector in zip(
            pending_positions,
            generated,
            strict=True,
        ):
            vectors[position] = vector
        embedded = len(pending_texts)

    dimension = int(source_dense.shape[1]) if source_dense.size else 0
    if vectors:
        dimension = max(
            dimension,
            max(len(vector) for vector in vectors if vector is not None),
        )
    dense = np.empty((len(vectors), dimension), dtype=np.float32)
    for index, vector in enumerate(vectors):
        if vector is None or len(vector) != dimension:
            raise ValueError("索引向量维度不一致")
        dense[index] = vector
    if len(dense):
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        dense = (dense / np.clip(norms, 1e-8, None)).astype(np.float32)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        pickle.dump({"chunks": chunks, "dense": dense}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, output_path)
    target_manifest = manifest_path or (
        output_path.parent / f"{output_path.stem}.manifest.json"
    )
    write_index_manifest(
        target_manifest,
        index_path=output_path,
        chunks=chunks,
        embedding_dim=dimension,
        model_id=model_id,
    )
    return IndexResult(
        chunks=len(chunks),
        embedded=embedded,
        reused=len(chunks) - embedded,
    )
