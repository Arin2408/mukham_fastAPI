import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mukham.settings')
django.setup()

from employees.models import Customuser, Attendance
from face_auth.models import EmployeeFaceData
from organisation.models import CustomUser as AuthUser
from shifts.models import Shift
from departments.models import Department
from designations.models import Designation
from locations.models import Location

def factory_reset():
    print("--- Starting Full Factory Reset ---")
    
    # 1. Clear Attendance & Shifts
    Attendance.objects.all().delete()
    Shift.objects.all().delete()
    print("Cleared Attendance and Shifts.")
    
    # 2. Clear Departments, Designations, Locations
    Department.objects.all().delete()
    Designation.objects.all().delete()
    Location.objects.all().delete()
    print("Cleared Departments, Designations, and Locations.")
    
    # 3. Clear Face Data
    EmployeeFaceData.objects.all().delete()
    print("Cleared Face Registration data.")
    
    # 4. Clear Employees
    Customuser.objects.all().delete()
    print("Cleared Employee profiles.")
    
    # 5. Clear Auth Users (Only non-organization accounts)
    # We MUST keep the organizations/admins or you won't be able to log in!
    non_org_users = AuthUser.objects.filter(is_organization=False)
    count = non_org_users.count()
    non_org_users.delete()
    print(f"Cleared {count} non-admin login accounts.")
    
    print("\n--- Factory Reset Complete. You have a clean slate! ---")

if __name__ == "__main__":
    factory_reset()
