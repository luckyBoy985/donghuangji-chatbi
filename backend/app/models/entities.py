from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


def new_id() -> str:
    return uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120), default="新分析")
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    shares: Mapped[list["ConversationShare"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ConversationShare(Base):
    __tablename__ = "conversation_shares"
    __table_args__ = (UniqueConstraint("conversation_id", "team_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="shares")


class Message(Base):
    __tablename__ = "message"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    generation_status: Mapped[str] = mapped_column(String(20), default="llm")
    model: Mapped[str] = mapped_column(String(120), default="none")
    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Citation(Base):
    __tablename__ = "citation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("message.id", ondelete="CASCADE"), index=True
    )
    citation_key: Mapped[str] = mapped_column(String(12))
    chunk_id: Mapped[str] = mapped_column(String(160))
    doc_id: Mapped[str] = mapped_column(String(160))
    product: Mapped[str] = mapped_column(String(80))
    section: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(40))
    published_at: Mapped[str] = mapped_column(String(40), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    used_in_answer: Mapped[bool] = mapped_column(Boolean, default=False)

    message: Mapped[Message] = relationship(back_populates="citations")


class Report(Base):
    __tablename__ = "report"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    products_json: Mapped[str] = mapped_column(Text, default="[]")
    markdown: Mapped[str] = mapped_column(Text)
    html: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="reports")
