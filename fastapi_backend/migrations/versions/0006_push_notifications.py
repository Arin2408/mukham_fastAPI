"""Push notifications: devices, preferences, sent log, push tickets

Revision ID: 0006_push_notifications
Revises: 0005_check_in_device_signals
Create Date: 2026-10-14

- push_devices: each signed-in phone's Expo push token, removed at sign-out
  or when Expo reports the app uninstalled.
- notification_preferences: per person, which kinds they want (all on
  until they switch one off).
- notifications_sent: one row per reminder sent, so a reminder for the
  same shift or check-in is never sent twice, however often the job runs.
- push_tickets: Expo's receipts are checked about 15 minutes later to
  remove tokens of uninstalled apps.
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_push_notifications"
down_revision = "0005_check_in_device_signals"
branch_labels = None
depends_on = None

USERS = "organisation_customuser.org_id"


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(USERS, ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token", name="uq_push_devices_token"),
    )
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"])

    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(USERS, ondelete="CASCADE"), primary_key=True),
        sa.Column("shift_start", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("check_out", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("new_task", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "notifications_sent",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(USERS, ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("ref", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "kind", "ref", name="uq_notifications_sent_once"),
    )

    op.create_table(
        "push_tickets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("push_tickets")
    op.drop_table("notifications_sent")
    op.drop_table("notification_preferences")
    op.drop_index("ix_push_devices_user_id", table_name="push_devices")
    op.drop_table("push_devices")
