"""Add enzymes table for restriction enzyme definitions.

Stores IUPAC recognition sites and cut positions.
Populated via hive-admin lib import.

Revision ID: 007
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "enzymes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True, index=True),
        sa.Column("site", sa.Text, nullable=False),
        sa.Column("cut5", sa.Integer, nullable=False),
        sa.Column("cut3", sa.Integer, nullable=False),
        sa.Column("overhang", sa.Integer, nullable=False),
        sa.Column("length", sa.Integer, nullable=False),
        sa.Column("is_palindrome", sa.Boolean, nullable=False),
        sa.Column("is_blunt", sa.Boolean, nullable=False),
    )


def downgrade():
    op.drop_table("enzymes")
