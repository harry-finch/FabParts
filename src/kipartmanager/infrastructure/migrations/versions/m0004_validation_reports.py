"""M5 scoped validation reports; previous catalogue and choices preserved."""

import sqlalchemy as sa
from alembic import op

revision = "0004_validation_reports"
down_revision = "0003_resource_choices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_reports",
        sa.Column("subject_key", sa.String(), primary_key=True),
        sa.Column("part_id", sa.Uuid(), sa.ForeignKey("parts.id")),
        sa.Column("collection_id", sa.Uuid(), sa.ForeignKey("collections.id")),
        sa.Column("report_json", sa.String(), nullable=False),
        sa.CheckConstraint(
            "(part_id IS NOT NULL) != (collection_id IS NOT NULL)", name="one_subject"
        ),
        sa.CheckConstraint(
            "subject_key = CASE WHEN part_id IS NOT NULL THEN 'Part:' || part_id "
            "ELSE 'Collection:' || collection_id END",
            name="subject_key_valid",
        ),
        sa.CheckConstraint("length(report_json) > 0", name="report_required"),
    )


def downgrade() -> None:
    op.drop_table("validation_reports")
