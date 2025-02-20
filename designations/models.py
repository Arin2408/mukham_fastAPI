from django.db import models
from departments.models import Department
class Designation(models.Model):
    designation_id = models.AutoField(primary_key=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    details = models.CharField(max_length=255)

    def __str__(self):
        return self.details
