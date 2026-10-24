from __future__ import annotations

from functools import lru_cache
from threading import Lock

import numpy as np

from backend.app.core.config import settings


class BgeM3Embedder:
    def __init__(self) -> None:
        self._model = None
        self._lock = Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            if not settings.bge_m3_path.exists():
                raise FileNotFoundError(f"BGE-M3 模型不存在：{settings.bge_m3_path}")
            from FlagEmbedding import BGEM3FlagModel

            self._model = BGEM3FlagModel(
                str(settings.bge_m3_path),
                use_fp16=settings.use_cuda,
            )

    def encode_query(self, query: str) -> np.ndarray:
        self._load()
        assert self._model is not None
        with self._lock:
            output = self._model.encode(
                [query],
                batch_size=1,
                max_length=512,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
        vector = np.asarray(output["dense_vecs"][0], dtype=np.float32)
        return vector / max(float(np.linalg.norm(vector)), 1e-8)

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, settings.embedding_dim), dtype=np.float32)
        self._load()
        assert self._model is not None
        with self._lock:
            output = self._model.encode(
                texts,
                batch_size=8,
                max_length=1024,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
        vectors = np.asarray(output["dense_vecs"], dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return (vectors / np.clip(norms, 1e-8, None)).astype(np.float32)


@lru_cache(maxsize=1)
def get_embedder() -> BgeM3Embedder:
    return BgeM3Embedder()
