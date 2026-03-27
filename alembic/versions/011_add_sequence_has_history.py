"""Add has_history boolean to sequences.

Revision ID: 011
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sequences",
        sa.Column("has_history", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    op.drop_column("sequences", "has_history")
