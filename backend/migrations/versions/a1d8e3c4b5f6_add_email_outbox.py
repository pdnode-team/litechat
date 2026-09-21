"""add email outbox

Revision ID: a1d8e3c4b5f6
Revises: c4f91a2b7d10
Create Date: 2026-09-20 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1d8e3c4b5f6"
down_revision: Union[str, Sequence[str], None] = "c4f91a2b7d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("to_address", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_outbox_status"), "email_outbox", ["status"], unique=False)
    op.create_index(
        op.f("ix_email_outbox_next_attempt_at"), "email_outbox", ["next_attempt_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_outbox_next_attempt_at"), table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_status"), table_name="email_outbox")
    op.drop_table("email_outbox")
