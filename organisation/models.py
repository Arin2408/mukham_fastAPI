from django.db import models
from django.contrib.auth.models import AbstractUser, PermissionsMixin, BaseUserManager
from django.utils.crypto import get_random_string
import random, string
class CustomUserManager(BaseUserManager):
    def create_user(self, mobile_number, email, password=None, **extra_fields):
        if not mobile_number:
            raise ValueError('Mobile number must be set')
        if not email:
            raise ValueError('Email must be set')
            
        email = self.normalize_email(email)
        
        # Generate password if not provided
        if not password:
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            
        user = self.model(
            mobile_number=mobile_number,
            email=email,
            **extra_fields
        )
        if password:
            user.set_password(password)
        else:
            generated_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            user.set_password(generated_password)
            user.temporary_password = generated_password
            
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_organization', True)
        return self.create_user(mobile_number, email, password, **extra_fields)

class CustomUser(AbstractUser):
    username = None
    first_name = None
    last_name = None
    
    org_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    details = models.TextField(blank=True, null=True)
    mobile_number = models.CharField(max_length=15, unique=True)
    is_organization = models.BooleanField(default=True)
    
    USERNAME_FIELD = 'mobile_number'
    REQUIRED_FIELDS = ['name', 'email']
    
    objects = CustomUserManager()
    
    def generate_password(self):
        """Generate and set random 8-character password"""
        random_pass = get_random_string(8)
        self.set_password(random_pass)
        return random_pass
    @property
    def user_type(self):
        return "organization" if self.is_organization else "employee"
    
    @property
    def user_id(self):
        if self.is_organization:
            return self.org_id
        return self.employee.pk if hasattr(self, 'employee') else None
    
    def __str__(self):
        return f"{self.name} ({self.mobile_number})"