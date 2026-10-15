"""Emails: one account per mailbox, whatever the letter case

Revision ID: 0008_email_unique_any_case
Revises: 0007_push_device_install_key
Create Date: 2026-10-15

- Existing emails are lowercased (the app now saves them that way).
- A unique index on lower(email): "Admin@Firm.com" and "admin@firm.com"
  can no longer be two accounts, so a password reset always finds one.

Stops, changing nothing, if two accounts already differ only by case: those
need merging or renaming by hand first (the error lists them).
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_email_unique_any_case"
down_revision = "0007_push_device_install_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    clashes = op.get_bind().execute(
        sa.text(
            "SELECT lower(email) FROM organisation_customuser "
            "GROUP BY lower(email) HAVING count(*) > 1"
        )
    ).scalars().all()
    if clashes:
        raise RuntimeError(
            "These emails belong to more than one account (differing only in "
            "upper/lower case). Merge or rename them, then run this again: "
            + ", ".join(clashes)
        )
    op.execute("UPDATE organisation_customuser SET email = lower(email) WHERE email <> lower(email)")
    op.create_index(
        "uq_customuser_email_lower",
        "organisation_customuser",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_customuser_email_lower", table_name="organisation_customuser")
