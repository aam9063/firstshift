"""Third-party document review flag on applications (F11 T4/S4).

The red-team report (evals/reports/redteam-v1.md) recorded that documents of
someone else were silently accepted into the preboarding tracker. These
columns carry the explicit review flag the inbound classification sets and
the People Ops clearance that releases the row-21 tracker hold.

Revises: 8c41f2b09d73
Create Date: 2026-10-23

"""

import sqlalchemy as sa

from alembic import op

revision = "b3f1c2a94d57"
down_revision = "8c41f2b09d73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "document_review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "applications",
        sa.Column("document_review_cleared_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("applications", "document_review_cleared_at")
    op.drop_column("applications", "document_review_required")
