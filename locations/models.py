from django.db import models
from organisation.models import CustomUser

class Location(models.Model):
    location_id = models.AutoField(primary_key=True)
    location_name = models.CharField(max_length=255)    
    latitude = models.DecimalField(max_digits=9, decimal_places=6)  
    longitude = models.DecimalField(max_digits=9, decimal_places=6) 
    org = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def __str__(self):
        return self.location_name