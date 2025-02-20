from django.db import models
from departments.models import Department

class Shift(models.Model):
    shift_id = models.AutoField(primary_key=True)
    shift_name = models.CharField(max_length=255)
    shift_start_time = models.TimeField()
    shift_end_time = models.TimeField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.shift_name} - {self.shift_start_time.strftime("%H:%M")} to {self.shift_end_time.strftime("%H:%M")}'
