"""Drop the tables only Django used

Revision ID: 0003_drop_django_tables
Revises: d8db55b3ce01
Create Date: 2026-10-13

Django is removed. These tables held its migration history, admin log,
sessions, content types, permissions, groups and DRF auth tokens. Nothing
in the FastAPI app reads them, and no app table references them.

A database built from 0000_baseline never had them, so each drop is
IF EXISTS. Not reversible: Django is gone, so downgrade does not recreate them.
"""
from alembic import op


revision = "0003_drop_django_tables"
down_revision = "d8db55b3ce01"
branch_labels = None
depends_on = None


# Referencing tables first, so no CASCADE is needed.
DJANGO_TABLES = [
    "django_admin_log",
    "django_session",
    "authtoken_token",
    "organisation_customuser_groups",
    "organisation_customuser_user_permissions",
    "auth_group_permissions",
    "auth_permission",
    "auth_group",
    "django_content_type",
    "django_migrations",
]


def upgrade() -> None:
    for table in DJANGO_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    pass
