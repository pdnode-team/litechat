"""add pending_email for email-change flow

Revision ID: b2e9f4d5c6a7
Revises: a1d8e3c4b5f6
Create Date: 2026-09-20 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2e9f4d5c6a7"
down_revision: Union[str, Sequence[str], None] = "a1d8e3c4b5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pending_email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "pending_email")
