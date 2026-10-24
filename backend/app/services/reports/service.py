from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from markdown_it import MarkdownIt
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.limits import (
    AsyncConcurrencyGate,
    QueueTimeoutError,
    get_gpu_gate,
)
from backend.app.models.entities import Conversation, Message, Report
from backend.app.services.data.models import Evidence
from backend.app.services.data.repository import get_repository
from backend.app.services.data.retrieval import RetrievalEngine
from backend.app.services.qa.citations import validate_citations
from backend.app.services.qa.llm import DeepSeekLLM, get_llm

REPORT_SECTIONS = (
    "摘要",
    "产品概况",
    "系统与玩法对比",
    "版本运营节奏",
    "机会与风险",
)

THEME_QUERIES = (
    "产品定位 平台 图鉴 基础信息",
    "养成 系统 玩法 差异 进化 升星",
    "版本 更新 运营 公告 维护 补偿",
    "优势 风险 商业化 付费 用户反馈 机会",
)


class ReportGenerationError(RuntimeError):
    pass


class ReportService:
    def __init__(
        self,
        retrieval: RetrievalEngine | object | None = None,
        llm: DeepSeekLLM | object | None = None,
        gate: AsyncConcurrencyGate | None = None,
    ) -> None:
        self.retrieval = retrieval or RetrievalEngine(get_repository())
        self.llm = llm or get_llm()
        self.gate = gate or get_gpu_gate()

    async def generate(
        self,
        db: Session,
        conversation: Conversation,
        products: list[str] | None = None,
    ) -> Report:
        try:
            async with self.gate.slot():
                return await self._generate(db, conversation, products)
        except QueueTimeoutError as error:
            raise ReportGenerationError(str(error)) from error

    async def _generate(
        self,
        db: Session,
        conversation: Conversation,
        products: list[str] | None = None,
    ) -> Report:
        selected_products = products or self._conversation_products(db, conversation.id)
        selected_products = selected_products or ["东煌纪"]
        hits = await asyncio.to_thread(
            self._collect_evidence,
            selected_products,
        )
        if not hits:
            raise ReportGenerationError("没有足够证据生成报告")

        context_messages = list(
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc())
                .limit(12)
            ).all()
        )
        history = [
            (message.role, message.content)
            for message in context_messages
            if message.role in {"user", "assistant"} and message.content
        ]
        prompt = (
            "生成一份竞品情报报告。严格使用以下五个 Markdown 二级标题："
            "## 摘要、## 产品概况、## 系统与玩法对比、## 版本运营节奏、"
            "## 机会与风险。每个事实句标注 [S编号]。"
        )
        try:
            generated = await self.llm.complete(prompt, hits, history)
        except Exception as error:
            raise ReportGenerationError("报告生成模型暂不可用") from error
        if not generated.strip():
            raise ReportGenerationError("报告生成模型返回空内容")

        valid_keys = {f"S{index}" for index in range(1, len(hits) + 1)}
        generated, _used = validate_citations(generated, valid_keys)
        generated = self._ensure_sections(generated)
        today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
        title = f"{'、'.join(selected_products)}竞品情报报告"
        evidence = "\n".join(
            f"- [S{index}] {hit.product} · {hit.section} · {hit.title}"
            for index, hit in enumerate(hits, start=1)
        )
        markdown = (
            f"# {title}\n\n"
            f"> 生成日期：{today}\n>\n"
            f"> 产品范围：{'、'.join(selected_products)}\n\n"
            f"{generated.strip()}\n\n"
            f"## 证据清单\n\n{evidence}\n"
        )
        md = MarkdownIt("commonmark", {"html": False}).enable("table")
        report = Report(
            conversation_id=conversation.id,
            title=title,
            products_json=json.dumps(selected_products, ensure_ascii=False),
            markdown=markdown,
            html=md.render(markdown),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report

    def _conversation_products(
        self, db: Session, conversation_id: str
    ) -> list[str]:
        messages = db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        ).all()
        if not messages:
            return []
        try:
            filters = json.loads(messages[0].filters_json or "{}")
        except json.JSONDecodeError:
            return []
        return list(filters.get("products") or [])

    def _collect_evidence(self, products: list[str]) -> list[Evidence]:
        unique: dict[str, Evidence] = {}
        for query in THEME_QUERIES:
            for hit in self.retrieval.search(
                query,
                products=products,
                sections=[],
                limit=5,
            ):
                unique.setdefault(hit.chunk_id, hit)
        return list(unique.values())[:16]

    @staticmethod
    def _ensure_sections(content: str) -> str:
        parts: Sequence[str] = [content.strip()]
        for section in REPORT_SECTIONS:
            if f"## {section}" not in content:
                parts = [*parts, f"## {section}\n\n当前资料未覆盖。"]
        return "\n\n".join(parts)


@lru_cache(maxsize=1)
def get_report_service() -> ReportService:
    return ReportService()
