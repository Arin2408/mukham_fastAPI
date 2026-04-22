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
    organisation = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE,
        related_name='employees',
        limit_choices_to={'is_organization': True}
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user.mobile_number})"
    
class Attendance(models.Model):
    STATUS_CHOICES = [
        ('Early', 'Early'),
        ('On Time', 'On Time'),
        ('Late', 'Late'),
    ]

    employee = models.ForeignKey(
        Customuser,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
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