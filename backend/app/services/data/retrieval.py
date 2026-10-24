from __future__ import annotations

from dataclasses import replace
from typing import Protocol

import numpy as np

from backend.app.core.config import settings
from backend.app.services.data.bm25 import BM25Index, tokenize
from backend.app.services.data.embedder import get_embedder
from backend.app.services.data.intent import expand_query, section_boost
from backend.app.services.data.models import Evidence
from backend.app.services.data.repository import DataRepository, get_repository
from backend.app.services.data.reranker import get_reranker


class Embedder(Protocol):
    def encode_query(self, query: str) -> np.ndarray: ...


class Reranker(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


def filter_evidence(
    hits: list[Evidence],
    products: list[str] | None,
    sections: list[str] | None,
) -> list[Evidence]:
    product_set = set(products or [])
    section_set = set(sections or [])
    return [
        hit
        for hit in hits
        if (not product_set or hit.product in product_set)
        and (not section_set or hit.section in section_set)
    ]


def rrf_fuse(rankings: list[list[Evidence]], k: int = 60) -> list[Evidence]:
    scores: dict[str, float] = {}
    by_id: dict[str, Evidence] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1.0 / (
                k + rank
            )
            by_id.setdefault(item.chunk_id, item)
    return [
        replace(by_id[chunk_id], score=score)
        for chunk_id, score in sorted(scores.items(), key=lambda item: -item[1])
    ]


def cosine_scores(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return np.empty(0, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-8:
        return np.zeros(len(matrix), dtype=np.float32)
    normalized = matrix / np.clip(
        np.linalg.norm(matrix, axis=1, keepdims=True), 1e-8, None
    )
    return normalized @ (vector / norm)


def diversify_results(
    candidates: list[Evidence],
    limit: int,
    products: list[str] | None,
) -> list[Evidence]:
    selected: list[Evidence] = []
    seen_documents: set[str] = set()
    selected_products = [product for product in (products or []) if product]

    if len(selected_products) > 1:
        buckets = {
            product: [item for item in candidates if item.product == product]
            for product in selected_products
        }
        cursors = {product: 0 for product in selected_products}
        while len(selected) < limit:
            progressed = False
            for product in selected_products:
                bucket = buckets[product]
                while cursors[product] < len(bucket):
                    item = bucket[cursors[product]]
                    cursors[product] += 1
                    if item.doc_id not in seen_documents:
                        selected.append(item)
                        seen_documents.add(item.doc_id)
                        progressed = True
                        break
                if len(selected) >= limit:
                    return selected
            if not progressed:
                break

    for item in candidates:
        if len(selected) >= limit:
            break
        if item.doc_id not in seen_documents:
            selected.append(item)
            seen_documents.add(item.doc_id)
    return selected


class RetrievalEngine:
    def __init__(
        self,
        repository: DataRepository | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.repository = repository or get_repository()
        self.embedder: Embedder = embedder or get_embedder()
        self.reranker: Reranker = reranker or get_reranker()
        self.bm25 = BM25Index(
            [
                f"{item.title} {item.section} {item.text}"
                for item in self.repository.evidence
            ]
        )
        self.last_degraded: list[str] = []
        self._repository_revision = self.repository.revision

    def _refresh_repository(self) -> None:
        if self.repository.refresh_if_changed():
            self.bm25 = BM25Index(
                [
                    f"{item.title} {item.section} {item.text}"
                    for item in self.repository.evidence
                ]
            )
        self._repository_revision = self.repository.revision

    def search(
        self,
        query: str,
        *,
        products: list[str] | None = None,
        sections: list[str] | None = None,
        limit: int = 8,
    ) -> list[Evidence]:
        self._refresh_repository()
        self.last_degraded = []
        product_scope = list(dict.fromkeys(products or []))
        scopes: list[tuple[str, list[int]]] = []
        if product_scope:
            for product in product_scope:
                product_indexes = [
                    index
                    for index, item in enumerate(self.repository.evidence)
                    if item.product == product
                    and (not sections or item.section in sections)
                ]
                if product_indexes:
                    scopes.append((product, product_indexes))
        else:
            all_indexes = [
                index
                for index, item in enumerate(self.repository.evidence)
                if not sections or item.section in sections
            ]
            if all_indexes:
                scopes.append(("", all_indexes))
        if not scopes:
            return []

        lexical_scores = self.bm25.scores(expand_query(query, products))
        query_vector: np.ndarray | None = None
        try:
            query_vector = self.embedder.encode_query(query)
        except Exception:
            self.last_degraded.append("bge")

        per_scope_limit = max(
            8, settings.qa_candidates // max(len(scopes), 1)
        )
        scope_rankings: list[list[Evidence]] = []
        all_lexical: list[Evidence] = []
        for _product, scope_indexes in scopes:
            lexical_indexes = sorted(
                scope_indexes,
                key=lambda index: -float(lexical_scores[index]),
            )[: max(per_scope_limit * 2, 20)]
            lexical = [
                replace(
                    self.repository.evidence[index],
                    score=float(lexical_scores[index]),
                )
                for index in lexical_indexes
                if lexical_scores[index] > 0
            ]
            all_lexical.extend(lexical)

            dense: list[Evidence] = []
            if query_vector is not None:
                semantic_scores = cosine_scores(
                    self.repository.dense[scope_indexes], query_vector
                )
                dense_positions = np.argsort(-semantic_scores)[
                    : max(per_scope_limit * 2, 20)
                ]
                dense = [
                    replace(
                        self.repository.evidence[scope_indexes[position]],
                        score=float(semantic_scores[position]),
                    )
                    for position in dense_positions
                ]
            local_fused = rrf_fuse(
                [ranking for ranking in (dense, lexical) if ranking]
            )
            locally_boosted = [
                replace(
                    item,
                    score=item.score + section_boost(query, item),
                )
                for item in local_fused
            ]
            locally_boosted.sort(key=lambda item: -item.score)
            scope_rankings.append(locally_boosted[:per_scope_limit])

        candidates: list[Evidence] = []
        candidate_ids: set[str] = set()
        for rank in range(max((len(items) for items in scope_rankings), default=0)):
            for ranking in scope_rankings:
                if rank >= len(ranking):
                    continue
                item = ranking[rank]
                if item.chunk_id not in candidate_ids:
                    candidates.append(item)
                    candidate_ids.add(item.chunk_id)
                if len(candidates) >= settings.qa_candidates:
                    break
            if len(candidates) >= settings.qa_candidates:
                break

        if not candidates:
            return []
        try:
            rerank_scores = self.reranker.score(
                query, [item.text for item in candidates]
            )
            lexical_max = max(
                (item.score for item in all_lexical), default=1.0
            )
            lexical_by_id = {
                item.chunk_id: min(float(item.score) / max(lexical_max, 1e-8), 1.0)
                for item in all_lexical
            }
            reranked = [
                replace(
                    item,
                    score=float(score) * 0.76
                    + lexical_by_id.get(item.chunk_id, 0.0) * 0.24
                    + section_boost(query, item),
                )
                for item, score in zip(candidates, rerank_scores, strict=True)
            ]
            reranked.sort(key=lambda item: -item.score)
        except Exception:
            self.last_degraded.append("reranker")
            reranked = self._fallback_scores(query, candidates)
        return diversify_results(reranked, max(1, min(limit, 20)), products)

    def _fallback_scores(
        self, query: str, candidates: list[Evidence]
    ) -> list[Evidence]:
        terms = tokenize(query)
        if not terms:
            return candidates
        scored: list[Evidence] = []
        for rank, item in enumerate(candidates, start=1):
            text = f"{item.title} {item.section} {item.text}"
            covered = sum(1 for term in terms if term in text) / len(terms)
            score = covered * (1.0 - min(rank, 50) / 100.0)
            scored.append(replace(item, score=score))
        return sorted(scored, key=lambda item: -item.score)

    def get_document(self, doc_id: str, chunk_id: str | None = None) -> dict:
        return self.repository.document(doc_id, chunk_id)

    def compare_products(
        self,
        products: list[str],
        aspects: list[str] | None = None,
        limit_per_product: int = 3,
    ) -> dict:
        results: dict[str, list[dict]] = {}
        for product in products:
            queries = aspects or [product]
            seen: set[str] = set()
            hits: list[Evidence] = []
            for query in queries:
                for hit in self.search(
                    query,
                    products=[product],
                    limit=limit_per_product,
                ):
                    if hit.chunk_id not in seen:
                        seen.add(hit.chunk_id)
                        hits.append(hit)
                    if len(hits) >= limit_per_product:
                        break
                if len(hits) >= limit_per_product:
                    break
            results[product] = [
                {
                    "chunk_id": hit.chunk_id,
                    "doc_id": hit.doc_id,
                    "title": hit.title,
                    "section": hit.section,
                    "text": hit.text,
                    "score": round(hit.score, 4),
                    "url": hit.url,
                }
                for hit in hits
            ]
        return {"products": results}
