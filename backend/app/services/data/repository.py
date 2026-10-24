from __future__ import annotations

import pickle
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

from backend.app.core.config import settings
from backend.app.services.data.models import Evidence
from backend.app.services.data.index_manifest import validate_index_manifest


class DataRepository:
    def __init__(
        self,
        index_path: Path,
        platform_path: Path | None = None,
        manifest_path: Path | None = None,
    ) -> None:
        self.index_path = index_path
        self.platform_path = platform_path
        self.manifest_path = manifest_path
        self.manifest: dict[str, Any] = {}
        self.manifest_status = "base"
        self.evidence: list[Evidence] = []
        self.dense = np.empty((0, settings.embedding_dim), dtype=np.float32)
        self._documents: dict[str, list[int]] = defaultdict(list)
        self._lock = Lock()
        self._loaded = False
        self._active_path: Path | None = None
        self._mtime_ns: int | None = None
        self.revision = 0

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._reload_locked()

    def _selected_path(self) -> Path:
        if self.platform_path is not None and self.platform_path.exists():
            return self.platform_path
        return self.index_path

    def refresh_if_changed(self) -> bool:
        with self._lock:
            if not self._loaded and self.evidence:
                self._loaded = True
                return False
            selected = self._selected_path()
            stamp = selected.stat().st_mtime_ns if selected.exists() else None
            if (
                self._loaded
                and selected == self._active_path
                and stamp == self._mtime_ns
            ):
                return False
            self._reload_locked()
            return True

    def _reload_locked(self) -> None:
        selected = self._selected_path()
        if not selected.exists():
            raise FileNotFoundError(f"检索索引不存在：{selected}")
        manifest: dict[str, Any] = {}
        manifest_status = "base"
        if selected == self.platform_path and self.manifest_path is not None:
            manifest = validate_index_manifest(
                selected,
                self.manifest_path,
            )
            manifest_status = "verified" if manifest else "legacy"
        with selected.open("rb") as handle:
            payload = pickle.load(handle)
        self.manifest = manifest
        self.manifest_status = manifest_status
        chunks = payload.get("chunks")
        dense = np.asarray(payload.get("dense"), dtype=np.float32)
        if not isinstance(chunks, list) or dense.ndim != 2:
            raise ValueError("检索索引格式无效")
        if dense.shape != (len(chunks), settings.embedding_dim):
            raise ValueError(
                f"检索索引维度不一致：{len(chunks)} 与 {dense.shape}"
            )
        norm = np.linalg.norm(dense, axis=1, keepdims=True)
        loaded_dense = (dense / np.clip(norm, 1e-8, None)).astype(np.float32)
        loaded_evidence: list[Evidence] = []
        documents: dict[str, list[int]] = defaultdict(list)
        for index, chunk in enumerate(chunks):
            item = Evidence(
                chunk_id=str(chunk["chunk_id"]),
                text=str(chunk.get("text", "")),
                product=str(chunk.get("product", "")),
                section=str(chunk.get("section", "")),
                doc_id=str(chunk.get("doc_id", "")),
                source_type=str(chunk.get("source_type", "")),
                title=str(chunk.get("title", "")),
                url=str(chunk.get("url", "")),
                published_at=str(chunk.get("published_at", "")),
            )
            loaded_evidence.append(item)
            documents[item.doc_id].append(index)
        self.dense = loaded_dense
        self.evidence = loaded_evidence
        self._documents = documents
        self._active_path = selected
        self._mtime_ns = selected.stat().st_mtime_ns
        self._loaded = True
        self.revision += 1

    def document(self, doc_id: str, chunk_id: str | None = None) -> dict[str, Any]:
        self.refresh_if_changed()
        indexes = self._documents.get(doc_id, [])
        if not indexes:
            raise KeyError(doc_id)
        selected = indexes
        if chunk_id:
            selected = [
                index
                for index in indexes
                if self.evidence[index].chunk_id == chunk_id
            ]
            if not selected:
                raise KeyError(chunk_id)
        chunks = [self._as_chunk(index) for index in selected]
        first = self.evidence[selected[0]]
        return {
            "doc_id": doc_id,
            "product": first.product,
            "section": first.section,
            "title": first.title,
            "source_type": first.source_type,
            "published_at": first.published_at,
            "url": first.url,
            "chunks": chunks,
        }

    def _as_chunk(self, index: int) -> dict[str, Any]:
        item = self.evidence[index]
        return {
            "chunk_id": item.chunk_id,
            "text": item.text,
        }


@lru_cache(maxsize=1)
def get_repository() -> DataRepository:
    repository = DataRepository(
        settings.index_path,
        settings.platform_index_path,
        settings.platform_manifest_path,
    )
    repository.load()
    return repository
