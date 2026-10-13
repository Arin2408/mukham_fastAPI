
from alembic import op
import sqlalchemy as sa


revision = "0002_security_tracking"
down_revision = "0001_manager_and_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "liveness_sessions",
        sa.Column("session_id", sa.String(length=128), primary_key=True),
        sa.Column("mobile_number", sa.String(length=15), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_liveness_sessions_mobile_number",
        "liveness_sessions",
        ["mobile_number"],
    )

    op.create_table(
        "revoked_refresh_tokens",
        sa.Column("jti", sa.String(length=128), primary_key=True),
        sa.Column("mobile_number", sa.String(length=15), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index(
        "ix_revoked_refresh_tokens_mobile_number",
        "revoked_refresh_tokens",
        ["mobile_number"],
    )

    op.create_index(
        "ix_revoked_refresh_tokens_expires_at",
        "revoked_refresh_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("revoked_refresh_tokens")
    op.drop_table("liveness_sessions")

