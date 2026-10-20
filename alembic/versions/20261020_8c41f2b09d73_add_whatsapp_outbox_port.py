"""Add whatsapp to the outbox_port enum (messaging channel messages go through the outbox).

Revision ID: 8c41f2b09d73
Revises: 751da69ac6df
Create Date: 2026-10-20

"""

from alembic import op

revision = "8c41f2b09d73"
down_revision = "751da69ac6df"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ allows ADD VALUE inside a transaction; the value is usable
    # from the next statement, which is all our inserts need.
    op.execute("ALTER TYPE outbox_port ADD VALUE IF NOT EXISTS 'whatsapp'")


def downgrade() -> None:
    # Postgres cannot remove an enum value; downgrade restores schema shape by
    # leaving the value in place. Documented as effectively irreversible.
    pass
