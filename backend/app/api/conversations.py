from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.access.policy import (
    conversation_permission,
    shared_conversation_ids,
    user_team_ids,
)
from backend.app.core.database import get_db
from backend.app.core.security import CurrentUser
from backend.app.models.entities import (
    Citation,
    Conversation,
    ConversationShare,
    Message,
    utc_now,
)
from backend.app.models.identity import Team
from backend.app.schemas.conversation import (
    CitationOut,
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    ConversationUpdate,
    MessageOut,
    ShareOut,
    ShareUpdate,
)
from backend.app.services.audit.service import record_audit

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _summary(conversation: Conversation, role: str = "owner") -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        owner_user_id=conversation.owner_user_id,
        access_role=role,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        generation_status=message.generation_status,
        model=message.model,
        created_at=message.created_at,
        citations=[
            CitationOut.model_validate(citation)
            for citation in sorted(message.citations, key=lambda item: item.citation_key)
        ],
    )


def accessible_conversation(
    db: Session,
    conversation_id: str,
    user,
    *,
    write: bool = False,
) -> tuple[Conversation, str]:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    role = conversation_permission(db, conversation, user)
    if role is None or (write and role != "owner"):
        raise HTTPException(
            status_code=404 if role is None else 403,
            detail="会话不存在" if role is None else "共享会话仅可只读访问",
        )
    return conversation, role


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationSummary:
    conversation = Conversation(
        owner_user_id=user.id,
        title=payload.title or "新分析",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _summary(conversation)


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    user: CurrentUser,
    scope: str = Query(default="mine", pattern=r"^(mine|shared)$"),
    db: Session = Depends(get_db),
) -> list[ConversationSummary]:
    if scope == "mine":
        rows = db.scalars(
            select(Conversation)
            .where(Conversation.owner_user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(100)
        ).all()
        return [_summary(item) for item in rows]
    shared_ids = shared_conversation_ids(db, user.id)
    if not shared_ids:
        return []
    rows = db.scalars(
        select(Conversation)
        .where(
            Conversation.id.in_(shared_ids),
            Conversation.owner_user_id != user.id,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    ).all()
    return [_summary(item, "read") for item in rows]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    conversation, role = accessible_conversation(db, conversation_id, user)
    summary = _summary(conversation, role)
    return ConversationDetail(
        **summary.model_dump(),
        messages=[
            _message_out(message)
            for message in sorted(
                conversation.messages, key=lambda item: item.created_at
            )
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationSummary:
    conversation, _role = accessible_conversation(
        db, conversation_id, user, write=True
    )
    conversation.title = payload.title
    conversation.updated_at = utc_now()
    db.commit()
    db.refresh(conversation)
    return _summary(conversation)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    conversation, _role = accessible_conversation(
        db, conversation_id, user, write=True
    )
    db.delete(conversation)
    db.commit()
    return Response(status_code=204)


@router.get("/{conversation_id}/shares", response_model=list[ShareOut])
def list_shares(
    conversation_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[ShareOut]:
    accessible_conversation(db, conversation_id, user, write=True)
    rows = db.execute(
        select(ConversationShare, Team)
        .join(Team, Team.id == ConversationShare.team_id)
        .where(ConversationShare.conversation_id == conversation_id)
        .order_by(Team.name)
    ).all()
    return [
        ShareOut(
            id=share.id,
            conversation_id=share.conversation_id,
            team_id=share.team_id,
            team_name=team.name,
            created_at=share.created_at,
        )
        for share, team in rows
    ]


@router.put("/{conversation_id}/shares", response_model=list[ShareOut])
def set_shares(
    conversation_id: str,
    payload: ShareUpdate,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[ShareOut]:
    accessible_conversation(db, conversation_id, user, write=True)
    requested = set(payload.team_ids)
    allowed = user_team_ids(db, user.id)
    if not requested.issubset(allowed):
        raise HTTPException(status_code=403, detail="只能共享给当前用户所属团队")
    db.execute(
        delete(ConversationShare).where(
            ConversationShare.conversation_id == conversation_id
        )
    )
    for team_id in requested:
        db.add(
            ConversationShare(
                conversation_id=conversation_id,
                team_id=team_id,
                created_by=user.id,
            )
        )
    record_audit(
        db,
        actor_user_id=user.id,
        action="conversation.share_update",
        resource_type="conversation",
        resource_id=conversation_id,
        metadata={"team_ids": sorted(requested)},
    )
    db.commit()
    return list_shares(conversation_id, user, db)


@router.post(
    "/{conversation_id}/clone",
    response_model=ConversationSummary,
    status_code=201,
)
def clone_conversation(
    conversation_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationSummary:
    source, _role = accessible_conversation(db, conversation_id, user)
    clone = Conversation(
        owner_user_id=user.id,
        title=f"{source.title} · 副本"[:120],
    )
    db.add(clone)
    db.flush()
    source_messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == source.id)
        .order_by(Message.created_at.asc())
    ).all()
    for source_message in source_messages:
        new_message = Message(
            conversation_id=clone.id,
            role=source_message.role,
            content=source_message.content,
            status=source_message.status,
            generation_status=source_message.generation_status,
            model=source_message.model,
            filters_json=source_message.filters_json,
        )
        db.add(new_message)
        db.flush()
        source_citations = db.scalars(
            select(Citation)
            .where(Citation.message_id == source_message.id)
            .order_by(Citation.citation_key)
        ).all()
        for citation in source_citations:
            db.add(
                Citation(
                    message_id=new_message.id,
                    citation_key=citation.citation_key,
                    chunk_id=citation.chunk_id,
                    doc_id=citation.doc_id,
                    product=citation.product,
                    section=citation.section,
                    title=citation.title,
                    source_type=citation.source_type,
                    published_at=citation.published_at,
                    url=citation.url,
                    snippet=citation.snippet,
                    score=citation.score,
                    used_in_answer=citation.used_in_answer,
                )
            )
    record_audit(
        db,
        actor_user_id=user.id,
        action="conversation.clone",
        resource_type="conversation",
        resource_id=clone.id,
        metadata={"source_id": source.id},
    )
    db.commit()
    db.refresh(clone)
    return _summary(clone)
