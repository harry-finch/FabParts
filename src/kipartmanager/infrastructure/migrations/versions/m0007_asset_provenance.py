"""M10.5 third-party provenance and redistribution facts, without changing M8."""

import sqlalchemy as sa
from alembic import op

revision = "0007_asset_provenance"
down_revision = "0006_documentation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("provenance_json", sa.String(), nullable=True))


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM assets WHERE provenance_json IS NOT NULL")
    ):
        raise RuntimeError(
            "Downgrade refused: asset provenance and redistribution facts would be lost."
        )
    op.drop_column("assets", "provenance_json")
