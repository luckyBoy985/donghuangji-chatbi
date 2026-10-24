from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.core.limits import (
    MemoryDailyQuota,
    RedisDailyQuota,
    get_daily_quota,
)
from backend.app.core.security import CurrentUser
from backend.app.api.conversations import accessible_conversation
from backend.app.access.policy import conversation_permission
from backend.app.models.entities import Conversation, Report
from backend.app.schemas.report import ReportCreate, ReportOut, ReportSummary
from backend.app.services.reports.service import (
    ReportGenerationError,
    ReportService,
    get_report_service,
)

router = APIRouter(prefix="/api", tags=["reports"])


def _report_out(report: Report) -> ReportOut:
    return ReportOut(
        id=report.id,
        conversation_id=report.conversation_id,
        title=report.title,
        products=json.loads(report.products_json or "[]"),
        markdown=report.markdown,
        html=report.html,
        created_at=report.created_at,
    )


@router.post(
    "/conversations/{conversation_id}/reports",
    response_model=ReportOut,
    status_code=201,
)
async def create_report(
    conversation_id: str,
    payload: ReportCreate,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: ReportService = Depends(get_report_service),
    quota: MemoryDailyQuota | RedisDailyQuota = Depends(get_daily_quota),
) -> ReportOut:
    conversation, _role = accessible_conversation(db, conversation_id, user, write=True)
    if not quota.consume(
        f"report:{user.id}",
        limit=settings.report_daily_limit_per_user,
    ):
        raise HTTPException(
            status_code=429,
            detail="今日报告生成额度已用完，请明天再试",
        )
    try:
        report = await service.generate(db, conversation, payload.products)
    except ReportGenerationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return _report_out(report)


@router.get("/reports", response_model=list[ReportSummary])
def list_reports(
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[Report]:
    reports = db.scalars(
        select(Report).order_by(Report.created_at.desc()).limit(200)
    ).all()
    accessible: list[Report] = []
    for report in reports:
        conversation = db.get(Conversation, report.conversation_id)
        if conversation and conversation_permission(db, conversation, user):
            accessible.append(report)
    return accessible[:100]


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> ReportOut:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    conversation = db.get(Conversation, report.conversation_id)
    if not conversation or not conversation_permission(db, conversation, user):
        raise HTTPException(status_code=404, detail="报告不存在")
    return _report_out(report)


@router.get("/reports/{report_id}/download.md")
def download_report(
    report_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    conversation = db.get(Conversation, report.conversation_id)
    if not conversation or not conversation_permission(db, conversation, user):
        raise HTTPException(status_code=404, detail="报告不存在")
    encoded_title = quote(f"{report.title}.md")
    return PlainTextResponse(
        report.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="report.md"; '
                f"filename*=UTF-8''{encoded_title}"
            )
        },
    )
