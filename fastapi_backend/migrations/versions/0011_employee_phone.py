"""One phone per employee

Revision ID: 0011_employee_phone
Revises: 0010_presence_events
Create Date: 2026-10-21

- device_id / device_registered_at: the phone this employee checks in
  from, saved by their first check-in from the app.
- pending_device_id: a different phone that tried to check in, waiting for
  the admin to approve it.
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_employee_phone"
down_revision = "0010_presence_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees_customuser",
        sa.Column("device_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "employees_customuser",
        sa.Column("device_registered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "employees_customuser",
        sa.Column("pending_device_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employees_customuser", "pending_device_id")
    op.drop_column("employees_customuser", "device_registered_at")
    op.drop_column("employees_customuser", "device_id")
