from rest_framework import serializers
from .models import Location

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['location_id','location_name', 'latitude', 'longitude', 'radius_meters', 'org']
        read_only_fields = ['location_id']