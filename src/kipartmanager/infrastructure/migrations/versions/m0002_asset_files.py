"""M2 managed-file identities; all M1 entities and associations are preserved."""

import sqlalchemy as sa
from alembic import op

revision = "0002_asset_files"
down_revision = "0001_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_files",
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("extension", sa.String(), nullable=False),
        sa.Column("original_name", sa.String(), nullable=False),
        sa.CheckConstraint(
            "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'", name="hash_valid"
        ),
        sa.CheckConstraint("typeof(size_bytes) = 'integer' AND size_bytes > 0", name="size_valid"),
        sa.CheckConstraint(
            "extension IN ('.pdf','.step','.stp','.wrl','.kicad_mod','.kicad_sym')",
            name="extension_valid",
        ),
        sa.CheckConstraint(
            "length(original_name) > 0 AND instr(original_name, '/') = 0 "
            "AND instr(original_name, char(92)) = 0 AND original_name NOT IN ('.','..')",
            name="name_valid",
        ),
    )


def downgrade() -> None:
    # Destructive to file associations; blobs are deliberately retained.
    op.drop_table("asset_files")
