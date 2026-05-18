import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mukham.settings')
django.setup()

from organisation.models import CustomUser

user = CustomUser.objects.filter(mobile_number='7010923446').first()
if user:
    print(f"Testing password 'admin123' for user {user.mobile_number}: {user.check_password('admin123')}")
else:
    print("User 7010923446 not found")
