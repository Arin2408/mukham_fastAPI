from django.db import models
import random, string
from departments.models import Department
from designations.models import Designation
from shifts.models import Shift
from locations.models import Location
from organisation.models import CustomUser

class Customuser(models.Model):
    user = models.OneToOneField(
        CustomUser, 
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='employee'
    )
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True)
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True)
    office_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True)
    photo = models.ImageField(upload_to='employee_photos/', null=True, blank=True)
    organisation = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE,
        related_name='employees',
        limit_choices_to={'is_organization': True}
    )
    member_password = models.CharField(max_length=255, blank=True, null=True)
    is_member_registered = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Auto-generate member_password if not already set
        if not self.member_password and hasattr(self, 'user') and self.first_name:
            from django.contrib.auth.hashers import make_password
            # First 5 digits of mobile number + First 5 letters of first name
            phone_part = self.user.mobile_number[:5] if self.user.mobile_number else ""
            name_part = self.first_name[:5]
            plain_password = f"{phone_part}{name_part}".lower()
            self.member_password = make_password(plain_password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user.mobile_number})"
    
class Attendance(models.Model):
    STATUS_CHOICES = [
        ('Early', 'Early'),
        ('On Time', 'On Time'),
        ('Late', 'Late'),
        ('FAILED_VERIFICATION', 'FAILED_VERIFICATION'),
    ]

    employee = models.ForeignKey(
        Customuser,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    location_status = models.CharField(max_length=10, choices=[('inside', 'inside'), ('outside', 'outside')], default='inside')
    face_status = models.CharField(max_length=10, choices=[('verified', 'verified'), ('failed', 'failed'), ('skipped', 'skipped')], default='skipped')
    hours_worked = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-check_in']

    def save(self, *args, **kwargs):
        if self.check_out and not self.hours_worked:
            self.calculate_hours()
        super().save(*args, **kwargs)

    def calculate_hours(self):
        if self.check_out:
            delta = self.check_out - self.check_in
            self.hours_worked = round(delta.total_seconds() / 3600, 2)

    def __str__(self):
        return f"{self.employee} - {self.check_in.date()}"