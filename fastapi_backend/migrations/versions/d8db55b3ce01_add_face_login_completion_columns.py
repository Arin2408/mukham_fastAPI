
from alembic import op
import sqlalchemy as sa


revision = "d8db55b3ce01"
down_revision = "97b2d85b9b68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "liveness_sessions",
        sa.Column("face_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "liveness_sessions",
        sa.Column("login_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("liveness_sessions", "login_completed_at")
    op.drop_column("liveness_sessions", "face_verified_at")

