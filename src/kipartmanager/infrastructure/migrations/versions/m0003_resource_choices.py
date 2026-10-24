"""M4 explicit resource choices; existing assets and links are preserved."""

import sqlalchemy as sa
from alembic import op

revision = "0003_resource_choices"
down_revision = "0002_asset_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_choices",
        sa.Column("owner_key", sa.String(), primary_key=True),
        sa.Column("asset_type", sa.String(), primary_key=True),
        sa.Column("part_id", sa.Uuid(), sa.ForeignKey("parts.id")),
        sa.Column("package_id", sa.Uuid(), sa.ForeignKey("packages.id")),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id")),
        sa.Column("reference_json", sa.String(), nullable=False),
        sa.CheckConstraint("(part_id IS NOT NULL) != (package_id IS NOT NULL)", name="one_owner"),
        sa.CheckConstraint("(asset_id IS NOT NULL) != (reference_json != '')", name="one_resource"),
        sa.CheckConstraint(
            "(part_id IS NOT NULL AND asset_type IN ('SYMBOL','DATASHEET')) OR "
            "(package_id IS NOT NULL AND asset_type IN ('FOOTPRINT','MODEL_3D'))",
            name="role_valid",
        ),
        sa.CheckConstraint(
            "owner_key = CASE WHEN part_id IS NOT NULL THEN 'Part:' || part_id "
            "ELSE 'Package:' || package_id END",
            name="owner_key_valid",
        ),
    )


def downgrade() -> None:
    # Drops explicit choices only; managed associations and bytes are kept.
    op.drop_table("resource_choices")
