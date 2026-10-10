from sqlalchemy.orm import Session, joinedload

from app.models.employee import Employee


def get_employee_profile(
    db: Session,
    user_id: int,
) -> Employee | None:
    return (
        db.query(Employee)
        .options(
            joinedload(Employee.department),
            joinedload(Employee.designation),
            joinedload(Employee.shift),
            joinedload(Employee.office_location),
        )
        .filter(Employee.user_id == user_id)
        .first()
    )