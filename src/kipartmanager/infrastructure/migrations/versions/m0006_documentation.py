"""M10 identification history and additive document records, preserving M0–M9 data."""

import sqlalchemy as sa
from alembic import op

revision = "0006_documentation"
down_revision = "0005_symbol_entry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "part_identifications",
        sa.Column("part_id", sa.Uuid(), sa.ForeignKey("parts.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data_json", sa.String(), nullable=False),
        sa.CheckConstraint("typeof(revision) = 'integer' AND revision > 0", name="revision_valid"),
        sa.CheckConstraint("length(data_json) > 0", name="data_required"),
    )
    op.create_table(
        "part_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("part_id", sa.Uuid(), sa.ForeignKey("parts.id"), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("data_json", sa.String(), nullable=False),
        sa.UniqueConstraint("part_id", "asset_id"),
        sa.CheckConstraint("length(data_json) > 0", name="data_required"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM part_identifications")) or connection.scalar(
        sa.text("SELECT count(*) FROM part_documents")
    ):
        raise RuntimeError("Downgrade refused: M10 identification/document history would be lost.")
    op.drop_table("part_documents")
    op.drop_table("part_identifications")
