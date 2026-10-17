from fastapi import APIRouter, Depends

# Sign-in lives in accounts.py: /org/login for admins, /member/login plus
# the face check for employees.
from app.dependencies.auth import get_current_user
from app.models.user import User


router = APIRouter()

@router.get("/auth/verify")
def verify_token(
    current_user: User = Depends(get_current_user),
):
    return {
        "valid": True,
        "mobile_number": current_user.mobile_number,
        "is_organization": current_user.is_organization,
        "role": "organization" if current_user.is_organization else "employee",
        # The organisation's id for admins (their profile is
        # /organisations/{org_id}); an employee's own account id otherwise.
        "org_id": current_user.org_id,
    }
