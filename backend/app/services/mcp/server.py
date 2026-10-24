from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastmcp import FastMCP

from backend.app.services.data.models import Evidence
from backend.app.services.data.repository import get_repository
from backend.app.services.data.retrieval import RetrievalEngine


def _hit(item: Evidence) -> dict[str, Any]:
    return {
        "chunk_id": item.chunk_id,
        "doc_id": item.doc_id,
        "product": item.product,
        "section": item.section,
        "title": item.title,
        "source_type": item.source_type,
        "published_at": item.published_at,
        "url": item.url,
        "text": item.text,
        "score": round(item.score, 4),
    }


def build_mcp_server(retrieval: RetrievalEngine | object | None = None) -> FastMCP:
    engine = retrieval or RetrievalEngine(get_repository())
    server = FastMCP(
        "东煌纪竞品情报",
        instructions="只读检索四个游戏产品的可追溯资料。",
        mask_error_details=True,
    )

    @server.tool
    def search_sources(
        query: str,
        products: list[str] | None = None,
        sections: list[str] | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """检索指定产品与栏目范围内的证据分块。"""
        hits = engine.search(
            query,
            products=products or [],
            sections=sections or [],
            limit=max(1, min(limit, 20)),
        )
        return {"query": query, "hits": [_hit(item) for item in hits]}

    @server.tool
    def get_document(
        doc_id: str,
        chunk_id: str | None = None,
    ) -> dict[str, Any]:
        """按文档或分块返回原文、分块和来源。"""
        return engine.get_document(doc_id, chunk_id)

    @server.tool
    def compare_products(
        products: list[str],
        aspects: list[str] | None = None,
        limit_per_product: int = 3,
    ) -> dict[str, Any]:
        """按产品和主题返回可引用的原始证据，不生成事实结论。"""
        return engine.compare_products(
            products,
            aspects or [],
            max(1, min(limit_per_product, 10)),
        )

    return server


@lru_cache(maxsize=1)
def get_mcp_server() -> FastMCP:
    return build_mcp_server()
