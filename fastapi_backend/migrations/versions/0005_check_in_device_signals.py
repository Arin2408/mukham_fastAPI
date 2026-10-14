"""Check-in device signals: GPS-faking flag and device ID

Revision ID: 0005_check_in_device_signals
Revises: 0004_refresh_token_families
Create Date: 2026-10-13

The mobile app reports whether Android detected a GPS-faking app and which
device checked in. Both are flagged for the admin, not used to reject a
check-in. Web check-ins leave them empty.
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_check_in_device_signals"
down_revision = "0004_refresh_token_families"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees_attendance",
        sa.Column("check_in_mocked", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "employees_attendance",
        sa.Column("check_in_device_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employees_attendance", "check_in_device_id")
    op.drop_column("employees_attendance", "check_in_mocked")
