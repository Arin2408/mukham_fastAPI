import os
import django
import sys

# Add the root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mukham.settings')
django.setup()

from employees.models import Customuser
from organisation.models import CustomUser as AuthUser

print(f"{'Name':<20} | {'Mobile':<12} | {'Org ID':<10} | {'Calculated Member Pass':<20}")
print("-" * 75)
for emp in Customuser.objects.all():
    phone_part = emp.user.mobile_number[:5] if emp.user.mobile_number else ""
    name_part = emp.first_name[:5]
    plain_pass = f"{phone_part}{name_part}".lower()
    print(f"{emp.first_name + ' ' + emp.last_name:<20} | {emp.user.mobile_number:<12} | {emp.organisation_id:<10} | {plain_pass:<20}")
