"""Add GIN trgm indexes for search performance.

Adds pg_trgm GIN indexes on:
- sequences.description (used in similarity scoring)
- part_instances.annotation_type (used in part search scoring)

These columns were searched via func.similarity() but lacked indexes,
causing sequential scans on every search query.

Revision ID: 006
Create Date: 2026-03-02
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX idx_seq_desc_trgm ON sequences
        USING gin (description gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX idx_pi_anntype_trgm ON part_instances
        USING gin (annotation_type gin_trgm_ops)
    """)


def downgrade():
    op.drop_index("idx_pi_anntype_trgm", table_name="part_instances")
    op.drop_index("idx_seq_desc_trgm", table_name="sequences")
