"""Add performance indexes on indexed_files.status and sequences.file_id.

Revision ID: 014
Create Date: 2026-04-01
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_file_status", "indexed_files", ["status"])
    op.create_index("idx_seq_file_id", "sequences", ["file_id"])


def downgrade():
    op.drop_index("idx_seq_file_id", table_name="sequences")
    op.drop_index("idx_file_status", table_name="indexed_files")
