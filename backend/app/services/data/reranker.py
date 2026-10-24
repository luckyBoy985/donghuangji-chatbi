from __future__ import annotations

from functools import lru_cache
from threading import Lock

from backend.app.core.config import settings


class BgeReranker:
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
            if not settings.bge_reranker_path.exists():
                raise FileNotFoundError(
                    f"BGE-Reranker 模型不存在：{settings.bge_reranker_path}"
                )
            from FlagEmbedding import FlagReranker

            self._model = FlagReranker(
                str(settings.bge_reranker_path),
                use_fp16=settings.use_cuda,
            )

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        self._load()
        assert self._model is not None
        with self._lock:
            raw = self._model.compute_score(
                [[query, passage] for passage in passages],
                normalize=True,
            )
        values = raw if isinstance(raw, list) else [raw]
        return [float(value) for value in values]


@lru_cache(maxsize=1)
def get_reranker() -> BgeReranker:
    return BgeReranker()
