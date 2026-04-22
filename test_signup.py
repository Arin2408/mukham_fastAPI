import os
import django
import requests

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mukham.settings')
django.setup()

from organisation.models import CustomUser
from rest_framework_simplejwt.tokens import RefreshToken

def test_signup():
    print("Testing Signup (Add Employee)...")
    
    # Get an organization user to act as the requester
    try:
        org_user = CustomUser.objects.get(mobile_number='919840308331')
    except CustomUser.DoesNotExist:
        print("Org user not found. Run migrations/seed first.")
        return

    # Generate JWT token for this org user
    refresh = RefreshToken.for_user(org_user)
    token = str(refresh.access_token)
    
    url = "http://127.0.0.1:8001/api/signup/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Payload similar to what frontend sends
    payload = {
        "first_name": "Test",
        "last_name": "Employee",
        "mobile_number": "9000000099", # Use a unique number
        "email": "test99@example.com", # Use a unique email
        "department": 1, # Adjust based on actual IDs
        "designation": 1,
        "shift": 1,
        "office_location": 1,
        "organisation": org_user.pk,
        "org_id": org_user.org_id
    }
    
    # Try to find valid IDs for dept/desig/shift/loc if 1 doesn't work
    from departments.models import Department
    from designations.models import Designation
    from shifts.models import Shift
    from locations.models import Location
    
    dept = Department.objects.filter(org=org_user).first()
    if dept: payload["department"] = dept.pk
    
    desig = Designation.objects.filter(department__org=org_user).first()
    if desig: payload["designation"] = desig.pk
    
    shift = Shift.objects.filter(org=org_user).first()
    if shift: payload["shift"] = shift.pk
    
    loc = Location.objects.filter(org=org_user).first()
    if loc: payload["office_location"] = loc.pk

    print(f"Payload: {payload}")
    
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

if __name__ == "__main__":
    test_signup()
