"""Durable, atomic TECH-03 ingestion receipts; no change to business entities."""

import sqlalchemy as sa
from alembic import op

revision = "0008_ingestion_operations"
down_revision = "0007_asset_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_sha256", sa.String(), nullable=False),
        sa.Column("part_id", sa.Uuid(), sa.ForeignKey("parts.id"), nullable=False),
        sa.CheckConstraint(
            "length(request_sha256) = 64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="request_sha256_valid",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM ingestion_operations")):
        raise RuntimeError("Downgrade refused: durable ingestion receipts would be lost.")
    op.drop_table("ingestion_operations")
