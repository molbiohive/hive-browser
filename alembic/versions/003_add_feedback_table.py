"""Add feedback table for team feedback collection.

Revision ID: 003
Create Date: 2026-02-23
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chat_id", sa.Text(), nullable=True),
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column(
            "priority", sa.Integer(), nullable=False, server_default="3"
        ),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_feedback_user", "feedback", ["user_id"])


def downgrade():
    op.drop_index("idx_feedback_user", table_name="feedback")
    op.drop_table("feedback")
