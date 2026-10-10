from app.db.session import SessionLocal
from app.models.employee import Employee
from app.models.user import User
from app.core.security import create_access_token


def main():
    db = SessionLocal()

    try:
        employee = (
            db.query(Employee)
            .join(
                User,
                User.org_id == Employee.user_id,
            )
            .filter(
                User.is_active == True,
            )
            .order_by(Employee.user_id)
            .first()
        )

        if employee is None:
            print("No active employee found in the database.")
            return

        user = (
            db.query(User)
            .filter(
                User.org_id == employee.user_id,
                User.is_active == True,
            )
            .first()
        )

        if user is None:
            print("Employee user account not found.")
            return

        token = create_access_token(
            mobile_number=user.mobile_number
        )

        print()
        print("Test employee:")
        print(f"user_id: {employee.user_id}")
        print(f"name: {employee.first_name} {employee.last_name}")
        print(f"mobile_number: {user.mobile_number}")
        print(f"organisation_id: {employee.organisation_id}")
        print(f"office_location_id: {employee.office_location_id}")
        print()
        print("ACCESS TOKEN:")
        print(token)
        print()

    finally:
        db.close()


if __name__ == "__main__":
    main()