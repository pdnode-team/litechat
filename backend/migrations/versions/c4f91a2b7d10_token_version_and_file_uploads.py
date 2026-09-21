"""token version and file uploads

Revision ID: c4f91a2b7d10
Revises: e08a745dcb1f
Create Date: 2026-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f91a2b7d10"
down_revision: Union[str, Sequence[str], None] = "e08a745dcb1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "file_uploads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("uploader_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_file_uploads_stored_name"), "file_uploads", ["stored_name"], unique=True)
    op.create_index(op.f("ix_file_uploads_uploader_id"), "file_uploads", ["uploader_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_file_uploads_uploader_id"), table_name="file_uploads")
    op.drop_index(op.f("ix_file_uploads_stored_name"), table_name="file_uploads")
    op.drop_table("file_uploads")
    op.drop_column("users", "token_version")
