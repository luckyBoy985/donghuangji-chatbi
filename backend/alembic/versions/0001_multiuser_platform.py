"""Create multiuser platform schema.

Revision ID: 0001_multiuser
Revises:
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_multiuser"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("username", sa.String(40), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("platform_role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "teams",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column("revoked_at", sa.String(40)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("last_seen_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)

    op.create_table(
        "team_memberships",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("team_id", sa.String(32), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("team_id", "user_id"),
    )
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"])
    op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"])

    op.create_table(
        "invitations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("team_id", sa.String(32), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_role", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.String(40)),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_invitations_code_hash", "invitations", ["code_hash"], unique=True)
    op.create_index("ix_invitations_team_id", "invitations", ["team_id"])

    op.create_table(
        "conversation",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_conversation_owner_user_id", "conversation", ["owner_user_id"])
    op.create_index("ix_conversation_owner_updated", "conversation", ["owner_user_id", "updated_at"])

    op.create_table(
        "message",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("conversation_id", sa.String(32), sa.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("generation_status", sa.String(20), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_message_conversation_id", "message", ["conversation_id"])

    op.create_table(
        "citation",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("message_id", sa.String(32), sa.ForeignKey("message.id", ondelete="CASCADE"), nullable=False),
        sa.Column("citation_key", sa.String(12), nullable=False),
        sa.Column("chunk_id", sa.String(160), nullable=False),
        sa.Column("doc_id", sa.String(160), nullable=False),
        sa.Column("product", sa.String(80), nullable=False),
        sa.Column("section", sa.String(160), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("published_at", sa.String(40), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("used_in_answer", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_citation_message_id", "citation", ["message_id"])

    op.create_table(
        "report",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("conversation_id", sa.String(32), sa.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("products_json", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_report_conversation_id", "report", ["conversation_id"])

    op.create_table(
        "conversation_shares",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("conversation_id", sa.String(32), sa.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.String(32), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("conversation_id", "team_id"),
    )
    op.create_index("ix_conversation_shares_conversation_id", "conversation_shares", ["conversation_id"])
    op.create_index("ix_conversation_shares_team_id", "conversation_shares", ["team_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("actor_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "migration_records",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stats_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_migration_records_source_hash", "migration_records", ["source_hash"], unique=True)


def downgrade() -> None:
    for table in (
        "migration_records",
        "audit_logs",
        "conversation_shares",
        "report",
        "citation",
        "message",
        "conversation",
        "invitations",
        "team_memberships",
        "user_sessions",
        "teams",
        "users",
    ):
        op.drop_table(table)
