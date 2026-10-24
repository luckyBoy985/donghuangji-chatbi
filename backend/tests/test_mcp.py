import asyncio

from fastmcp import Client

from backend.app.services.data.models import Evidence
from backend.app.services.mcp.server import build_mcp_server


class FakeMCPRetrieval:
    def search(self, _query, *, products=None, sections=None, limit=8):
        return [
            Evidence(
                chunk_id="chunk-m1",
                text="灵兽属性与克制资料",
                product=products[0] if products else "东煌纪",
                section="灵兽图鉴",
                score=0.9,
                doc_id="hero-1",
                title="灵兽档案",
                source_type="official",
            )
        ][:limit]

    def get_document(self, doc_id, chunk_id=None):
        return {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "chunks": [{"chunk_id": "chunk-m1", "text": "灵兽属性与克制资料"}],
        }

    def compare_products(self, products, aspects, limit_per_product):
        return {
            "products": {
                product: [{"chunk_id": "chunk-m1", "title": "灵兽档案"}]
                for product in products
            }
        }


def test_mcp_exposes_only_read_tools_and_applies_product_filter():
    async def exercise():
        server = build_mcp_server(FakeMCPRetrieval())
        async with Client(server) as mcp_client:
            tools = await mcp_client.list_tools()
            assert {tool.name for tool in tools} == {
                "search_sources",
                "get_document",
                "compare_products",
            }
            result = await mcp_client.call_tool(
                "search_sources",
                {
                    "query": "灵兽属性",
                    "products": ["东煌纪"],
                    "sections": [],
                    "limit": 5,
                },
            )
            payload = result.structured_content or {}
            assert payload["hits"][0]["product"] == "东煌纪"

    asyncio.run(exercise())
