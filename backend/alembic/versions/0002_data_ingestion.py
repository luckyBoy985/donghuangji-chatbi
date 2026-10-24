"""Add data source, ingestion job, document and chunk tables.

Revision ID: 0002_ingestion
Revises: 0001_multiuser
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_ingestion"
down_revision = "0001_multiuser"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("crawler_key", sa.String(64), nullable=True, unique=True),
        sa.Column("product", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("last_run_at", sa.String(40), nullable=True),
        sa.Column(
            "created_by",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )

    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("product", sa.String(80), nullable=False),
        sa.Column("section", sa.String(160), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("original_name", sa.String(300), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column(
            "source_id",
            sa.String(64),
            sa.ForeignKey("data_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("stats_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=True),
        sa.Column("finished_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_ingest_jobs_kind", "ingest_jobs", ["kind"])
    op.create_index("ix_ingest_jobs_status", "ingest_jobs", ["status"])

    op.create_table(
        "data_documents",
        sa.Column("doc_id", sa.String(180), primary_key=True),
        sa.Column("product", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("section", sa.String(160), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("published_at", sa.String(40), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("original_name", sa.String(300), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column(
            "source_id",
            sa.String(64),
            sa.ForeignKey("data_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    for column in ("product", "source_type", "section", "content_hash", "status", "origin"):
        op.create_index(f"ix_data_documents_{column}", "data_documents", [column])

    op.create_table(
        "data_chunks",
        sa.Column("chunk_id", sa.String(200), primary_key=True),
        sa.Column(
            "doc_id",
            sa.String(180),
            sa.ForeignKey("data_documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("doc_id", "ordinal"),
    )
    op.create_index("ix_data_chunks_doc_id", "data_chunks", ["doc_id"])


def downgrade() -> None:
    op.drop_table("data_chunks")
    op.drop_table("data_documents")
    op.drop_table("ingest_jobs")
    op.drop_table("data_sources")
