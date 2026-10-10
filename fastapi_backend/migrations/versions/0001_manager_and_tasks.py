"""Employee reporting manager and task tracking

Revision ID: 0001_manager_and_tasks
Revises:
Create Date: 2026-10-09

- employees_customuser.manager_id: the employee this employee reports to.
  NULL means the employee reports directly to the organisation admin
  (the top of the reporting tree).
- tasks_task: tasks assigned to employees, with assigned / due /
  completed dates for the task calendar.

Delete rules are enforced in the database (not only in Python) so a delete
from Django or from FastAPI behaves the same way.
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_manager_and_tasks"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # Reporting manager
    # ---------------------------------------------------------------
    op.add_column(
        "employees_customuser",
        sa.Column("manager_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "employees_customuser_manager_id_fk",
        "employees_customuser",
        "employees_customuser",
        ["manager_id"],
        ["user_id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "employees_customuser_manager_not_self",
        "employees_customuser",
        "manager_id IS NULL OR manager_id <> user_id",
    )
    op.create_index(
        "employees_customuser_manager_id_idx",
        "employees_customuser",
        ["manager_id"],
    )

    # ---------------------------------------------------------------
    # Tasks
    # ---------------------------------------------------------------
    op.create_table(
        "tasks_task",
        sa.Column("task_id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organisation_customuser.org_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("employees_customuser.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "priority",
            sa.String(10),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "status",
            sa.String(12),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("assigned_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("organisation_customuser.org_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high')",
            name="tasks_task_priority_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed')",
            name="tasks_task_status_valid",
        ),
        sa.CheckConstraint(
            "due_date IS NULL OR due_date >= assigned_date",
            name="tasks_task_due_after_assigned",
        ),
        sa.CheckConstraint(
            "completed_date IS NULL OR completed_date >= assigned_date",
            name="tasks_task_completed_after_assigned",
        ),
        sa.CheckConstraint(
            "(status = 'completed') = (completed_date IS NOT NULL)",
            name="tasks_task_completed_has_date",
        ),
    )
    op.create_index(
        "tasks_task_org_assigned_idx",
        "tasks_task",
        ["org_id", "assigned_date"],
    )
    op.create_index(
        "tasks_task_employee_idx",
        "tasks_task",
        ["employee_id"],
    )


def downgrade() -> None:
    op.drop_index("tasks_task_employee_idx", table_name="tasks_task")
    op.drop_index("tasks_task_org_assigned_idx", table_name="tasks_task")
    op.drop_table("tasks_task")

    op.drop_index(
        "employees_customuser_manager_id_idx",
        table_name="employees_customuser",
    )
    op.drop_constraint(
        "employees_customuser_manager_not_self",
        "employees_customuser",
        type_="check",
    )
    op.drop_constraint(
        "employees_customuser_manager_id_fk",
        "employees_customuser",
        type_="foreignkey",
    )
    op.drop_column("employees_customuser", "manager_id")
