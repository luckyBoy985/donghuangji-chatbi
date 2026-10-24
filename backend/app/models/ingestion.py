from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base
from backend.app.models.entities import new_id, utc_now


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="crawler")
    crawler_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    product: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="active")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    last_run_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now)


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    product: Mapped[str] = mapped_column(String(80), default="")
    section: Mapped[str] = mapped_column(String(160), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    original_name: Mapped[str] = mapped_column(String(300), default="")
    object_key: Mapped[str] = mapped_column(String(1024), default="")
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="等待后台处理")
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DataDocument(Base):
    __tablename__ = "data_documents"

    doc_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    product: Mapped[str] = mapped_column(String(80), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    section: Mapped[str] = mapped_column(String(160), default="", index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    published_at: Mapped[str] = mapped_column(String(40), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    original_name: Mapped[str] = mapped_column(String(300), default="")
    object_key: Mapped[str] = mapped_column(String(1024), default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    origin: Mapped[str] = mapped_column(String(20), default="baseline", index=True)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now)

    chunks: Mapped[list["DataChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DataChunk.ordinal",
    )


class DataChunk(Base):
    __tablename__ = "data_chunks"
    __table_args__ = (UniqueConstraint("doc_id", "ordinal"),)

    chunk_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("data_documents.doc_id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), default="")

    document: Mapped[DataDocument] = relationship(back_populates="chunks")
