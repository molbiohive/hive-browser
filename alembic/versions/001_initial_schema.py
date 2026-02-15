"""Initial schema — indexed_files, sequences, features, primers with pg_trgm.

Revision ID: 001
Create Date: 2026-02-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Enable trigram extension for fuzzy search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "indexed_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_path", sa.Text(), nullable=False, unique=True),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_mtime", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "file_id",
            sa.Integer(),
            sa.ForeignKey("indexed_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("size_bp", sa.Integer(), nullable=False),
        sa.Column("topology", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Trigram index on sequence name for fuzzy search
    op.execute(
        "CREATE INDEX idx_seq_name_trgm ON sequences USING gin (name gin_trgm_ops)"
    )
    # GIN index on JSONB meta for @> containment queries
    op.create_index("idx_seq_meta", "sequences", ["meta"], postgresql_using="gin")

    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "seq_id",
            sa.Integer(),
            sa.ForeignKey("sequences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("strand", sa.SmallInteger(), nullable=False),
        sa.Column("qualifiers", postgresql.JSONB(), nullable=True),
    )

    op.execute(
        "CREATE INDEX idx_feat_name_trgm ON features USING gin (name gin_trgm_ops)"
    )
    op.create_index("idx_feat_type", "features", ["type"])

    op.create_table(
        "primers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "seq_id",
            sa.Integer(),
            sa.ForeignKey("sequences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Text(), nullable=False),
        sa.Column("tm", sa.Float(), nullable=True),
        sa.Column("start", sa.Integer(), nullable=True),
        sa.Column("end", sa.Integer(), nullable=True),
        sa.Column("strand", sa.SmallInteger(), nullable=True),
    )


def downgrade():
    op.drop_table("primers")
    op.drop_table("features")
    op.drop_table("sequences")
    op.drop_table("indexed_files")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
