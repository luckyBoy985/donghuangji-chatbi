from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.limits import (
    AsyncConcurrencyGate,
    QueueTimeoutError,
    get_gpu_gate,
)
from backend.app.models.entities import Citation, Conversation, Message, utc_now
from backend.app.services.data.gate import assess_sufficiency
from backend.app.services.data.models import Evidence
from backend.app.services.data.repository import get_repository
from backend.app.services.data.retrieval import RetrievalEngine
from backend.app.services.qa.citations import validate_citations
from backend.app.services.qa.llm import DeepSeekLLM, get_llm

from sqlalchemy.orm import Session

REFUSAL_PREFIX = "当前资料不足以回答这个问题。"


class QAService:
    def __init__(
        self,
        retrieval: RetrievalEngine | object | None = None,
        llm: DeepSeekLLM | object | None = None,
        gate: AsyncConcurrencyGate | None = None,
    ) -> None:
        self.retrieval = retrieval or RetrievalEngine(get_repository())
        self.llm = llm or get_llm()
        self.gate = gate or get_gpu_gate()

    async def stream_answer(
        self,
        db: Session,
        conversation: Conversation,
        question: str,
        products: list[str],
        sections: list[str],
    ) -> AsyncIterator[dict]:
        try:
            async with self.gate.slot():
                async for item in self._stream_answer(
                    db,
                    conversation,
                    question,
                    products,
                    sections,
                ):
                    yield item
        except QueueTimeoutError as error:
            yield {
                "event": "error",
                "data": {
                    "code": "queue_timeout",
                    "message": str(error),
                },
            }

    async def _stream_answer(
        self,
        db: Session,
        conversation: Conversation,
        question: str,
        products: list[str],
        sections: list[str],
    ) -> AsyncIterator[dict]:
        question = question.strip()
        filters = {"products": products, "sections": sections}
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=question,
            status="completed",
            generation_status="none",
            model=settings.llm_model,
            filters_json=json.dumps(filters, ensure_ascii=False),
        )
        db.add(user_message)
        db.commit()

        yield {
            "event": "stage",
            "data": {"stage": "retrieving", "message": "正在检索资料"},
        }
        hits = await asyncio.to_thread(
            self.retrieval.search,
            question,
            products=products,
            sections=sections,
            limit=settings.qa_top_k,
        )
        yield {
            "event": "stage",
            "data": {"stage": "assessing", "message": "正在核验证据"},
        }
        verdict = assess_sufficiency(
            question,
            hits,
            strong=settings.qa_strong_score,
            minimum=settings.qa_min_score,
            overlap=settings.qa_min_overlap,
        )
        citation_keys = {
            f"S{index}" for index in range(1, len(hits) + 1)
        }

        if not verdict.sufficient:
            answer = f"{REFUSAL_PREFIX}{verdict.reason}。"
            assistant = self._save_assistant(
                db,
                conversation,
                answer,
                "refused",
                "refused",
                hits,
                set(),
            )
            yield {"event": "token", "data": {"delta": answer}}
            yield {
                "event": "citations",
                "data": {"citations": self._citation_payload(hits, set())},
            }
            yield {
                "event": "done",
                "data": {
                    "message_id": assistant.id,
                    "status": "refused",
                    "generation_status": "refused",
                },
            }
            return

        history_rows = list(
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc())
            ).all()
        )
        history = [
            (item.role, item.content)
            for item in history_rows[:-1]
            if item.role in {"user", "assistant"} and item.content
        ]

        yield {
            "event": "stage",
            "data": {"stage": "generating", "message": "正在生成回答"},
        }
        parts: list[str] = []
        generation_status = "llm"
        try:
            async for token in self.llm.stream(question, hits, history):
                if token:
                    parts.append(token)
                    yield {"event": "token", "data": {"delta": token}}
        except Exception:
            generation_status = "extractive"
            fallback = self._extractive_answer(hits)
            parts = [fallback]
            yield {
                "event": "warning",
                "data": {
                    "code": "llm_unavailable",
                    "message": "生成模型不可用，已切换为资料摘录",
                },
            }
            yield {"event": "token", "data": {"delta": fallback}}

        raw_answer = "".join(parts).strip()
        cleaned, used = validate_citations(raw_answer, citation_keys)
        if not used:
            generation_status = "extractive"
            cleaned = raw_answer + self._evidence_suffix(hits)
            used = {f"S{index}" for index in range(1, min(len(hits), 3) + 1)}

        yield {
            "event": "stage",
            "data": {"stage": "validating", "message": "正在校验引用"},
        }
        assistant = self._save_assistant(
            db,
            conversation,
            cleaned,
            "completed",
            generation_status,
            hits,
            used,
        )
        payload = self._citation_payload(hits, used)
        yield {"event": "citations", "data": {"citations": payload}}
        yield {
            "event": "done",
            "data": {
                "message_id": assistant.id,
                "status": "completed",
                "generation_status": generation_status,
            },
        }

    def _save_assistant(
        self,
        db: Session,
        conversation: Conversation,
        answer: str,
        status: str,
        generation_status: str,
        hits: list[Evidence],
        used: set[str],
    ) -> Message:
        assistant = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            status=status,
            generation_status=generation_status,
            model=settings.llm_model if generation_status == "llm" else "none",
            filters_json="{}",
        )
        db.add(assistant)
        db.flush()
        for index, hit in enumerate(hits, start=1):
            key = f"S{index}"
            db.add(
                Citation(
                    message_id=assistant.id,
                    citation_key=key,
                    chunk_id=hit.chunk_id,
                    doc_id=hit.doc_id,
                    product=hit.product,
                    section=hit.section,
                    title=hit.title,
                    source_type=hit.source_type,
                    published_at=hit.published_at,
                    url=hit.url,
                    snippet=hit.text[:1200],
                    score=hit.score,
                    used_in_answer=key in used,
                )
            )
        conversation.updated_at = utc_now()
        db.commit()
        db.refresh(assistant)
        return assistant

    @staticmethod
    def _citation_payload(
        hits: list[Evidence], used: set[str]
    ) -> list[dict]:
        return [
            {
                "citation_key": f"S{index}",
                "chunk_id": hit.chunk_id,
                "doc_id": hit.doc_id,
                "product": hit.product,
                "section": hit.section,
                "title": hit.title,
                "source_type": hit.source_type,
                "published_at": hit.published_at,
                "url": hit.url,
                "snippet": hit.text[:1200],
                "score": round(hit.score, 4),
                "used_in_answer": f"S{index}" in used,
            }
            for index, hit in enumerate(hits, start=1)
        ]

    @staticmethod
    def _extractive_answer(hits: list[Evidence]) -> str:
        excerpts = "\n\n".join(
            f"[S{index}] **{hit.title}**\n\n{hit.text[:500]}"
            for index, hit in enumerate(hits[:3], start=1)
        )
        return f"生成模型不可用，以下为资料摘录。\n\n{excerpts}"

    @staticmethod
    def _evidence_suffix(hits: list[Evidence]) -> str:
        if not hits:
            return ""
        items = "\n".join(
            f"- [S{index}] {hit.title}"
            for index, hit in enumerate(hits[:3], start=1)
        )
        return f"\n\n**参考证据**\n{items}"


@lru_cache(maxsize=1)
def get_qa_service() -> QAService:
    return QAService()
