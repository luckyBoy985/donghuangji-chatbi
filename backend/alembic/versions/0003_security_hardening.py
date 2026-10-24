"""Add forced password changes and login attempt tracking.

Revision ID: 0003_security
Revises: 0002_ingestion
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_security"
down_revision = "0002_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("attempt_key", sa.String(64), nullable=False),
        sa.Column("failed_at", sa.String(40), nullable=False),
    )
    op.create_index(
        "ix_login_attempts_attempt_key",
        "login_attempts",
        ["attempt_key"],
    )
    op.create_index(
        "ix_login_attempts_failed_at",
        "login_attempts",
        ["failed_at"],
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_column("users", "must_change_password")
