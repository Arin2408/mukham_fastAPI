"""Stored files: photos and face images kept in the database

Revision ID: 0009_stored_files
Revises: 0008_email_unique_any_case
Create Date: 2026-10-19

- stored_files: one row per employee photo ("media/...") or enrolled face
  image ("faces/..."), used when MEDIA_STORAGE is "database" (the default
  without an S3 bucket). Hosts such as Render's free plan wipe their disk
  on every restart, which lost the files kept there.
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_stored_files"
down_revision = "0008_email_unique_any_case"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("stored_files")
