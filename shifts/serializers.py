from rest_framework import serializers
from .models import Shift
from django.core.validators import MinValueValidator, MaxValueValidator

class ShiftSerializer(serializers.ModelSerializer):
    shift_start_time = serializers.TimeField(format='%H:%M', input_formats=['%H:%M'])
    shift_end_time = serializers.TimeField(format='%H:%M', input_formats=['%H:%M'])
    
    class Meta:
        model = Shift
        fields = '__all__'
        extra_kwargs = {
            'department': {'required': True}
        }

    def validate(self, data):
        if data['shift_start_time'] >= data['shift_end_time']:
            raise serializers.ValidationError("Shift end time must be after shift start time")
        return data