import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mukham.settings')
django.setup()

from organisation.models import CustomUser

print("Listing all users:")
for user in CustomUser.objects.all():
    print(f"Name: {user.name}, Mobile: {user.mobile_number}, Email: {user.email}, Is Org: {user.is_organization}")
