import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mukham.settings')
django.setup()

from employees.models import Customuser
from organisation.models import CustomUser as AuthUser
from django.contrib.auth.hashers import check_password

def debug_user_password(mobile_number):
    print(f"--- Debugging Password for {mobile_number} ---")
    try:
        # Normalize mobile
        normalized = ''.join(filter(str.isdigit, str(mobile_number)))[-10:]
        auth_user = AuthUser.objects.get(mobile_number=normalized)
        employee = Customuser.objects.get(user=auth_user)
        
        phone_part = auth_user.mobile_number[:5]
        name_part = employee.first_name[:5]
        expected_plain = f"{phone_part}{name_part}".lower()
        
        print(f"Name in DB: {employee.first_name} {employee.last_name}")
        print(f"Mobile in DB: {auth_user.mobile_number}")
        print(f"Expected Plain Password: {expected_plain}")
        
        if employee.member_password:
            is_correct = check_password(expected_plain, employee.member_password)
            print(f"Does it match hashed password in DB? {'YES' if is_correct else 'NO'}")
            if not is_correct:
                 print("ERROR: The hashed password in DB does not match the expected plain text!")
        else:
            print("ERROR: member_password field is EMPTY in DB!")

    except AuthUser.DoesNotExist:
        print(f"User with mobile {mobile_number} NOT FOUND.")
    except Customuser.DoesNotExist:
        print(f"Employee profile for {mobile_number} NOT FOUND.")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    # The user mentioned 44444mages, so trying with a phone that starts with 44444
    # I'll try to find any user whose mobile starts with 44444
    users = AuthUser.objects.filter(mobile_number__startswith='44444')
    if users.exists():
        for u in users:
            debug_user_password(u.mobile_number)
    else:
        print("No user found starting with 44444. Checking all users...")
        for u in AuthUser.objects.filter(is_organization=False)[:5]:
            debug_user_password(u.mobile_number)
