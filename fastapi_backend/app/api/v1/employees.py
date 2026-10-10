
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.employee import Employee
from app.models.user import User

from app.schemas.employee import (
    EmployeeResponse,
    EmployeeCreateRequest,
    EmployeeUpdateRequest,
    EmployeeCreateResponse,
    EmployeeCardResponse,
    HierarchyResponse,
    ManagerUpdateRequest,
)

from app.services.employee_service import (
    get_employee,
    get_employees,
    serialize_employee,
    create_employee,
    update_employee,
    delete_employee,
    media_url,
    get_hierarchy,
    set_manager,
)


router = APIRouter()


# --------------------------------------------------
# LIST EMPLOYEES
# GET /api/v1/employees
# --------------------------------------------------

@router.get(
    "/employees",
    response_model=list[EmployeeResponse],
)
def list_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )

    employees = get_employees(
        db=db,
        org_id=current_user.org_id,
    )

    return [
        serialize_employee(employee)
        for employee in employees
    ]


# --------------------------------------------------
# CREATE EMPLOYEE
# POST /api/v1/employees
# --------------------------------------------------

@router.post(
    "/employees",
    response_model=EmployeeCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_employee(
    data: EmployeeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )

    employee, plain_password = create_employee(
        db=db,
        org_id=current_user.org_id,
        data=data,
    )

    result = serialize_employee(employee)
    result["member_password"] = plain_password

    return result


# --------------------------------------------------
# GET SINGLE EMPLOYEE
# GET /api/v1/employees/{employee_id}
# --------------------------------------------------

@router.get(
    "/employees/{employee_id}",
    response_model=EmployeeResponse,
)
def retrieve_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )

    employee = get_employee(
        db=db,
        employee_id=employee_id,
        org_id=current_user.org_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return serialize_employee(employee)


# --------------------------------------------------
# UPDATE EMPLOYEE
# PUT /api/v1/employees/{employee_id}
# --------------------------------------------------

@router.put(
    "/employees/{employee_id}",
    response_model=EmployeeResponse,
)
def edit_employee(
    employee_id: int,
    data: EmployeeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )

    employee = get_employee(
        db=db,
        employee_id=employee_id,
        org_id=current_user.org_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    employee = update_employee(
        db=db,
        employee=employee,
        org_id=current_user.org_id,
        data=data,
    )

    return serialize_employee(employee)


# --------------------------------------------------
# DELETE EMPLOYEE
# DELETE /api/v1/employees/{employee_id}
# --------------------------------------------------

@router.delete(
    "/employees/{employee_id}",
    status_code=status.HTTP_200_OK,
)
def remove_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )

    employee = get_employee(
        db=db,
        employee_id=employee_id,
        org_id=current_user.org_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    delete_employee(db, employee)

    return {"message": "Deleted successfully"}


# --------------------------------------------------
# PUBLIC ID-CARD VERIFICATION
# GET /api/v1/employees/{employee_id}/card
# --------------------------------------------------
# Used by the QR code on the virtual ID card. No login, so it returns
# only what is printed on the card - never mobile number or email.

@router.get(
    "/employees/{employee_id}/card",
    response_model=EmployeeCardResponse,
)
def employee_card(
    employee_id: int,
    db: Session = Depends(get_db),
):
    employee = (
        db.query(Employee)
        .filter(Employee.user_id == employee_id)
        .first()
    )

    if employee is None or employee.user is None or not employee.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return {
        "employee_id": employee.user_id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "designation_name": (
            employee.designation.details if employee.designation else None
        ),
        "department_name": (
            employee.department.details if employee.department else None
        ),
        "organisation_name": (
            employee.organisation.name if employee.organisation else None
        ),
        "photo": media_url(employee.photo),
    }


def _require_org(current_user: User) -> None:
    if not current_user.is_organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access required",
        )


# --------------------------------------------------
# REPORTING TREE
# GET /api/v1/employee-hierarchy
# --------------------------------------------------
# Flat list with manager_id; the org chart page builds the tree. The
# organisation admin is the root - employees with manager_id null report
# directly to it.

@router.get(
    "/employee-hierarchy",
    response_model=HierarchyResponse,
)
def employee_hierarchy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_org(current_user)

    return {
        "organisation_id": current_user.org_id,
        "organisation_name": current_user.name,
        "employees": get_hierarchy(db, current_user.org_id),
    }


# --------------------------------------------------
# CHANGE REPORTING MANAGER
# PUT /api/v1/employees/{employee_id}/manager
# --------------------------------------------------

@router.put(
    "/employees/{employee_id}/manager",
    response_model=EmployeeResponse,
)
def change_manager(
    employee_id: int,
    data: ManagerUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_org(current_user)

    employee = get_employee(
        db=db,
        employee_id=employee_id,
        org_id=current_user.org_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    employee = set_manager(
        db=db,
        employee=employee,
        org_id=current_user.org_id,
        manager_id=data.manager_id,
    )

    return serialize_employee(employee)
