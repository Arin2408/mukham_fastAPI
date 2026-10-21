"""Presence events: leaving and returning to the office during a shift

Revision ID: 0010_presence_events
Revises: 0009_stored_files
Create Date: 2026-10-21

- presence_events: what the phone's background geofence reported during an
  open check-in ("exit" / "enter" the office area, tracking "on" / "off").
  Removed with its attendance row.
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_presence_events"
down_revision = "0009_stored_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "presence_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "attendance_id",
            sa.Integer(),
            sa.ForeignKey("employees_attendance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(10), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_presence_events_attendance_id", "presence_events", ["attendance_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_presence_events_attendance_id", table_name="presence_events")
    op.drop_table("presence_events")
