import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mukham.settings')
django.setup()

from employees.models import Customuser
from organisation.models import CustomUser as AuthUser

def clear_all_employees():
    print("Starting cleanup of all employees...")
    
    # Find all employee profiles
    employees = Customuser.objects.all()
    count = employees.count()
    
    if count == 0:
        print("No employees found to delete.")
        return

    # Delete associated AuthUser accounts first (where is_organization is False)
    # We filter by is_organization=False to ensure we don't accidentally delete admin accounts
    auth_users = AuthUser.objects.filter(is_organization=False)
    auth_count = auth_users.count()
    
    print(f"Deleting {count} employee profiles and {auth_count} login accounts...")
    
    # Customuser is linked via OneToOne with CASCADE, so deleting AuthUser should delete Customuser
    # But to be safe, we'll delete them both
    employees.delete()
    auth_users.delete()
    
    print("Cleanup complete. All employees have been removed.")

if __name__ == "__main__":
    clear_all_employees()
