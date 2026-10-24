from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.core.limits import (
    MemoryDailyQuota,
    RedisDailyQuota,
    get_daily_quota,
)
from backend.app.core.security import CurrentUser
from backend.app.core.runtime import current_request_id
from backend.app.api.conversations import accessible_conversation
from backend.app.models.entities import Conversation
from backend.app.schemas.message import MessageRequest
from backend.app.services.qa.service import QAService, get_qa_service

router = APIRouter(prefix="/api/conversations", tags=["messages"])


def _sse(event: str, data: dict) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


@router.post("/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str,
    payload: MessageRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: QAService = Depends(get_qa_service),
    quota: MemoryDailyQuota | RedisDailyQuota = Depends(get_daily_quota),
) -> StreamingResponse:
    conversation, _role = accessible_conversation(db, conversation_id, user, write=True)
    if not quota.consume(
        f"qa:{user.id}",
        limit=settings.qa_daily_limit_per_user,
    ):
        raise HTTPException(
            status_code=429,
            detail="今日问答额度已用完，请明天再试",
        )

    async def stream():
        try:
            async for item in service.stream_answer(
                db,
                conversation,
                payload.content,
                payload.products,
                payload.sections,
            ):
                yield _sse(item["event"], item["data"])
        except Exception as error:
            yield _sse(
                "error",
                {
                    "code": "stream_failed",
                    "message": f"本轮处理失败：{type(error).__name__}",
                    "request_id": current_request_id(),
                },
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
