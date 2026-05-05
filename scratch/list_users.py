import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mukham.settings')
django.setup()

from organisation.models import CustomUser
from employees.models import Customuser as EmployeeProfile

print("--- Organisation Users ---")
for user in CustomUser.objects.all():
    print(f"Name: {user.name}, Mobile: {user.mobile_number}, Email: {user.email}, IsOrg: {user.is_organization}")

print("\n--- Employee Profiles ---")
for emp in EmployeeProfile.objects.all():
    print(f"First Name: {emp.first_name}, User Mobile: {emp.user.mobile_number}, Member Password Set: {bool(emp.member_password)}")
