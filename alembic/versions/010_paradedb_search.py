"""Replace pg_trgm with ParadeDB BM25 search.

Drop trgm GIN indexes, add search_text column to sequences,
create BM25 indexes on sequences and part_names.

Revision ID: 010
Revises: 009
Create Date: 2026-03-17
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    # Enable pg_search (ParadeDB)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    # Add search_text column
    op.add_column("sequences", sa.Column("search_text", sa.Text, nullable=True))

    # Drop all trgm indexes
    op.drop_index("idx_seq_name_trgm", table_name="sequences")
    op.drop_index("idx_seq_desc_trgm", table_name="sequences")
    op.drop_index("idx_partname_trgm", table_name="part_names")
    op.drop_index("idx_pi_anntype_trgm", table_name="part_instances")

    # Drop pg_trgm extension
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

    # Create BM25 indexes
    op.execute("""
        CREATE INDEX idx_seq_bm25 ON sequences
        USING bm25 (id, name, description, search_text, topology, molecule, length)
        WITH (key_field='id')
    """)
    op.execute("""
        CREATE INDEX idx_pn_bm25 ON part_names
        USING bm25 (id, name)
        WITH (key_field='id')
    """)


def downgrade():
    # Drop BM25 indexes
    op.execute("DROP INDEX IF EXISTS idx_seq_bm25")
    op.execute("DROP INDEX IF EXISTS idx_pn_bm25")

    # Restore pg_trgm
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Recreate trgm indexes
    op.execute("""
        CREATE INDEX idx_seq_name_trgm ON sequences
        USING gin (name gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX idx_seq_desc_trgm ON sequences
        USING gin (description gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX idx_partname_trgm ON part_names
        USING gin (name gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX idx_pi_anntype_trgm ON part_instances
        USING gin (annotation_type gin_trgm_ops)
    """)

    # Drop search_text column
    op.drop_column("sequences", "search_text")

    # Drop pg_search extension
    op.execute("DROP EXTENSION IF EXISTS pg_search")
