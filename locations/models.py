from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from organisation.models import CustomUser

class Location(models.Model):
    location_id = models.AutoField(primary_key=True)
    location_name = models.CharField(max_length=255)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('-90')), MaxValueValidator(Decimal('90'))]
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('-180')), MaxValueValidator(Decimal('180'))]
    )
    org = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    # Geofence radius for check-in at this office
    radius_meters = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(10), MaxValueValidator(5000)]
    )

    def __str__(self):
        return self.location_name