"""Add collections table for enzyme/primer sets.

Global collections of enzymes or primers. Users select their active
collection via preferences.

Revision ID: 008
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "collections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("set_type", sa.Text, nullable=False),
        sa.Column("items", sa.JSON, nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_collection_type", "collections", ["set_type"])


def downgrade():
    op.drop_index("idx_collection_type", table_name="collections")
    op.drop_table("collections")
