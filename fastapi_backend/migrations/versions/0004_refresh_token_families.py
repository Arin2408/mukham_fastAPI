"""Refresh-token families: one per signed-in device

Revision ID: 0004_refresh_token_families
Revises: 0003_drop_django_tables
Create Date: 2026-10-13

Each login starts a family; every rotated refresh token keeps its
family_id. Signing out, or presenting an already-used refresh token,
revokes the family, so all of that device's refresh tokens stop working.
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_refresh_token_families"
down_revision = "0003_drop_django_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_token_families",
        sa.Column("family_id", sa.String(length=64), primary_key=True),
        sa.Column("mobile_number", sa.String(length=15), nullable=False),
        sa.Column("device_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=20), nullable=True),
    )

    op.create_index(
        "ix_refresh_token_families_mobile_number",
        "refresh_token_families",
        ["mobile_number"],
    )


def downgrade() -> None:
    op.drop_table("refresh_token_families")
