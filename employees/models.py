from django.db import models
import random, string
from departments.models import Department
from designations.models import Designation
from shifts.models import Shift
from locations.models import Location
from organisation.models import CustomUser

class Customuser(models.Model):
    mobile_number = models.CharField(max_length=10, unique=True, blank=False)
    password = models.CharField(max_length=255, blank=True)
    first_name = models.CharField(max_length=255, default='Default First Name')
    last_name = models.CharField(max_length=255, default='Default Last Name')
    email = models.EmailField(unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True)
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True)
    office_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True)
    organisation = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        if not self.password:
            self.password = self.generate_password()
        super(Customuser, self).save(*args, **kwargs)

    def generate_password(self):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.mobile_number})"