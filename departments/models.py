from django.db import models
from organisation.models import CustomUser
from locations.models import Location

class Department(models.Model):
    department_id = models.AutoField(primary_key=True)
    org = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    details = models.CharField(max_length=255)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)

    def __str__(self):
        return self.details