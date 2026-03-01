"""Parts and Libraries -- canonical sequence identity system.

Drop features/primers tables, add parts/part_names/part_instances/
libraries/library_members/annotations. Add sequence_hash/molecule/length
to sequences.

Revision ID: 005
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    # Drop old tables
    op.drop_table("primers")
    op.drop_table("features")

    # Add new columns to sequences
    op.add_column("sequences", sa.Column("sequence_hash", sa.Text(), nullable=True))
    op.add_column("sequences", sa.Column("molecule", sa.Text(), nullable=True, server_default="DNA"))
    op.add_column("sequences", sa.Column("length", sa.Integer(), nullable=True))

    # Populate from existing data
    op.execute("UPDATE sequences SET length = size_bp WHERE length IS NULL")
    op.execute("""
        UPDATE sequences SET molecule = COALESCE(
            meta::jsonb->>'molecule_type', 'DNA'
        ) WHERE molecule IS NULL
    """)
    # sequence_hash will be populated by re-ingest

    # Drop old size_bp column
    op.drop_column("sequences", "size_bp")

    # Make columns non-nullable after population
    op.alter_column("sequences", "length", nullable=False)
    op.alter_column("sequences", "molecule", nullable=False, server_default=None)
    op.alter_column("sequences", "sequence_hash", nullable=False, server_default="")

    op.create_index("idx_seq_hash", "sequences", ["sequence_hash"])

    # Create parts table
    op.create_table(
        "parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sequence_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("sequence", sa.Text(), nullable=False),
        sa.Column("molecule", sa.Text(), nullable=False),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_part_hash", "parts", ["sequence_hash"])

    # Create part_names table
    op.create_table(
        "part_names",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("parts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("part_id", "name", "source", name="uq_part_name_source"),
    )
    op.execute("""
        CREATE INDEX idx_partname_trgm ON part_names
        USING gin (name gin_trgm_ops)
    """)

    # Create part_instances table
    op.create_table(
        "part_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("parts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq_id", sa.Integer(), sa.ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("annotation_type", sa.Text(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=True),
        sa.Column("end", sa.Integer(), nullable=True),
        sa.Column("strand", sa.SmallInteger(), nullable=True),
        sa.Column("qualifiers", sa.JSON(), nullable=True),
    )
    op.create_index("idx_pi_seq_start", "part_instances", ["seq_id", "start"])
    op.create_index("idx_pi_part", "part_instances", ["part_id"])

    # Create libraries table
    op.create_table(
        "libraries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create library_members table
    op.create_table(
        "library_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("library_id", sa.Integer(), sa.ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("parts.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("library_id", "part_id", name="uq_library_part"),
    )

    # Create annotations table
    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("parts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
    )
    op.create_index("idx_annotation_part_key", "annotations", ["part_id", "key"])


def downgrade():
    op.drop_table("annotations")
    op.drop_table("library_members")
    op.drop_table("libraries")
    op.drop_table("part_instances")
    op.drop_table("part_names")
    op.drop_table("parts")

    op.drop_index("idx_seq_hash", table_name="sequences")
    op.drop_column("sequences", "sequence_hash")
    op.drop_column("sequences", "molecule")

    # Restore size_bp from length
    op.add_column("sequences", sa.Column("size_bp", sa.Integer()))
    op.execute("UPDATE sequences SET size_bp = length")
    op.alter_column("sequences", "size_bp", nullable=False)
    op.drop_column("sequences", "length")

    # Recreate features table
    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seq_id", sa.Integer(), sa.ForeignKey("sequences.id", ondelete="CASCADE")),
        sa.Column("name", sa.Text()),
        sa.Column("type", sa.Text()),
        sa.Column("start", sa.Integer()),
        sa.Column("end", sa.Integer()),
        sa.Column("strand", sa.SmallInteger()),
        sa.Column("qualifiers", sa.JSON(), nullable=True),
    )

    # Recreate primers table
    op.create_table(
        "primers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seq_id", sa.Integer(), sa.ForeignKey("sequences.id", ondelete="CASCADE")),
        sa.Column("name", sa.Text()),
        sa.Column("sequence", sa.Text()),
        sa.Column("tm", sa.Float(), nullable=True),
        sa.Column("start", sa.Integer(), nullable=True),
        sa.Column("end", sa.Integer(), nullable=True),
        sa.Column("strand", sa.SmallInteger(), nullable=True),
    )
