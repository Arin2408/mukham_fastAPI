"""Push devices: install key, so a push address can't be moved by someone else

Revision ID: 0007_push_device_install_key
Revises: 0006_push_notifications
Create Date: 2026-10-15

- push_devices.install_key_hash: SHA-256 of a secret the app makes once per
  install. Moving an address to another person needs the same secret, which
  only the phone itself has. Empty for rows from older app builds.
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_push_device_install_key"
down_revision = "0006_push_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("push_devices", sa.Column("install_key_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("push_devices", "install_key_hash")
