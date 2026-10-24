"""Initial M1 schema. Definitions are frozen independently of current ORM models."""

import sqlalchemy as sa
from alembic import op

revision = "0001_catalogue"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("inventories", "locations", "collections"):
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.UniqueConstraint("name"),
            sa.CheckConstraint("length(trim(name)) > 0", name="name_required"),
        )
    op.create_table(
        "packages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_required"),
    )
    op.create_table(
        "parts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("package_id", sa.Uuid(), sa.ForeignKey("packages.id")),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_required"),
        sa.CheckConstraint("state IN ('DRAFT', 'IDENTIFIED', 'DEPRECATED')", name="state_valid"),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("validation_state", sa.String(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_required"),
        sa.CheckConstraint(
            "asset_type IN ('SYMBOL','FOOTPRINT','MODEL_3D','DATASHEET')", name="type_valid"
        ),
        sa.CheckConstraint(
            "origin IN ('USER_PROVIDED','KICAD_OFFICIAL','MANAGED_LIBRARY',"
            "'MANUFACTURER','TRUSTED_THIRD_PARTY','GENERATED_PARAMETRIC','GENERATED_AI')",
            name="origin_valid",
        ),
        sa.CheckConstraint("validation_state = 'UNCHECKED'", name="validation_unchecked"),
    )
    op.create_table(
        "stock_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("part_id", sa.Uuid(), sa.ForeignKey("parts.id"), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), sa.ForeignKey("inventories.id"), nullable=False),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("locations.id")),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("part_id", "inventory_id"),
        sa.CheckConstraint("typeof(quantity) = 'integer' AND quantity >= 0", name="quantity_valid"),
    )
    for name, owner, target, owner_table, target_table in (
        ("part_assets", "part_id", "asset_id", "parts", "assets"),
        ("package_assets", "package_id", "asset_id", "packages", "assets"),
        ("collection_parts", "collection_id", "part_id", "collections", "parts"),
    ):
        op.create_table(
            name,
            sa.Column(owner, sa.Uuid(), sa.ForeignKey(f"{owner_table}.id"), primary_key=True),
            sa.Column(target, sa.Uuid(), sa.ForeignKey(f"{target_table}.id"), primary_key=True),
        )


def downgrade() -> None:
    # Destructive on populated data; application never calls this automatically.
    for name in (
        "collection_parts",
        "package_assets",
        "part_assets",
        "stock_items",
        "assets",
        "parts",
        "packages",
        "collections",
        "locations",
        "inventories",
    ):
        op.drop_table(name)
