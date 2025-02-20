from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.crypto import get_random_string

class CustomUser(AbstractUser):
    # Remove default fields
    username = None
    first_name = None
    last_name = None
    email = None  
    # Custom fields
    org_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    details = models.TextField(blank=True, null=True)
    mobile_number = models.CharField(max_length=15, unique=True)
    
    USERNAME_FIELD = 'mobile_number'
    REQUIRED_FIELDS = ['name']

    def generate_password(self):
        """Generate and set random 8-character password"""
        random_pass = get_random_string(8)
        self.set_password(random_pass)
        return random_pass

    def __str__(self):
        return f"{self.name} ({self.mobile_number})"