from sqlalchemy.orm import Session, joinedload

from app.models.employee import Employee


def get_employee_with_location(
    db: Session,
    employee_id: int,
) -> Employee | None:
    return (
        db.query(Employee)
        .options(
            joinedload(Employee.office_location)
        )
        .filter(
            Employee.user_id == employee_id
        )
        .first()
    )