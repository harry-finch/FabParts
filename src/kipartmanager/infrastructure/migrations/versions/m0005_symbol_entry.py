"""M8 portable managed copies of selected official symbol entries."""

import sqlalchemy as sa
from alembic import op

revision = "0005_symbol_entry"
down_revision = "0004_validation_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_files", sa.Column("symbol_name", sa.String(), nullable=False, server_default="")
    )
    with op.batch_alter_table("asset_files") as batch:
        batch.create_check_constraint(
            "symbol_entry", "symbol_name = '' OR extension = '.kicad_sym'"
        )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM asset_files WHERE symbol_name != ''")):
        raise RuntimeError("Downgrade refused: selected symbol entries would be lost.")
    with op.batch_alter_table("asset_files") as batch:
        batch.drop_constraint("symbol_entry", type_="check")
        batch.drop_column("symbol_name")
