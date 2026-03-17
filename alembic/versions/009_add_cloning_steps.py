"""Add cloning_steps table for SnapGene cloning history.

Stores the DAG of cloning operations (Gibson, restriction, PCR, etc.)
parsed from SnapGene history trees.

Revision ID: 009
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cloning_steps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "sequence_id", sa.Integer,
            sa.ForeignKey("sequences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.Integer, nullable=False),
        sa.Column(
            "parent_step_id", sa.Integer,
            sa.ForeignKey("cloning_steps.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String, nullable=False, server_default=""),
        sa.Column("operation", sa.String, nullable=False, server_default="invalid"),
        sa.Column("seq_len", sa.Integer, server_default="0"),
        sa.Column("circular", sa.Boolean, server_default="false"),
        sa.Column("molecule_type", sa.String, server_default="DNA"),
        sa.Column("oligos", sa.JSON, server_default="[]"),
        sa.Column("enzymes", sa.JSON, server_default="[]"),
        sa.Column("features", sa.JSON, server_default="[]"),
        sa.Column("primers", sa.JSON, server_default="[]"),
        sa.Column("parameters", sa.JSON, server_default="{}"),
    )
    op.create_index(
        "idx_cloning_steps_seq", "cloning_steps", ["sequence_id"],
    )
    op.create_unique_constraint(
        "uq_cloning_step_seq_node", "cloning_steps",
        ["sequence_id", "node_id"],
    )


def downgrade():
    op.drop_constraint("uq_cloning_step_seq_node", "cloning_steps", type_="unique")
    op.drop_index("idx_cloning_steps_seq", table_name="cloning_steps")
    op.drop_table("cloning_steps")
