"""Add tool_approvals table for quarantine system.

Revision ID: 004
Create Date: 2026-02-23
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tool_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.Text(), unique=True, nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default="quarantined"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("tool_approvals")
