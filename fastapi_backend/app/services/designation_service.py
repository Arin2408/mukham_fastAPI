from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.designation import Designation


def get_designations(
    db: Session,
    org_id: int,
) -> list[Designation]:
    return (
        db.query(Designation)
        .join(
            Department,
            Designation.department_id == Department.department_id,
        )
        .filter(
            Department.org_id == org_id
        )
        .order_by(Designation.designation_id)
        .all()
    )


def create_designation(
    db: Session,
    department: Department,
    details: str,
) -> Designation:
    designation = Designation(
        department_id=department.department_id,
        details=details,
    )

    db.add(designation)
    db.commit()
    db.refresh(designation)

    return designation


def update_designation(
    db: Session,
    designation: Designation,
    department: Department | None = None,
    details: str | None = None,
) -> Designation:

    if department is not None:
        designation.department_id = department.department_id

    if details is not None:
        designation.details = details

    db.commit()
    db.refresh(designation)

    return designation


def delete_designation(
    db: Session,
    designation: Designation,
) -> None:
    db.delete(designation)
    db.commit()