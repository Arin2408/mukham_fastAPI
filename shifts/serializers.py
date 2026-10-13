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
        # On partial updates, fall back to the existing values
        instance = self.instance
        start = data.get('shift_start_time', getattr(instance, 'shift_start_time', None))
        end = data.get('shift_end_time', getattr(instance, 'shift_end_time', None))
        department = data.get('department', getattr(instance, 'department', None))
        name = (data.get('shift_name', getattr(instance, 'shift_name', '')) or '').strip()

        # End before start is allowed: it is an overnight shift (e.g. 20:00 -> 04:00 next day).
        # Only a zero-length shift is invalid.
        if start == end:
            raise serializers.ValidationError("Shift start and end time cannot be the same")

        # Prevent duplicate shifts within the same department
        siblings = Shift.objects.filter(department=department)
        if instance:
            siblings = siblings.exclude(pk=instance.pk)

        if siblings.filter(shift_name__iexact=name).exists():
            raise serializers.ValidationError(
                f'A shift named "{name}" already exists in this department'
            )

        if siblings.filter(shift_start_time=start, shift_end_time=end).exists():
            raise serializers.ValidationError(
                f'A shift from {start.strftime("%H:%M")} to {end.strftime("%H:%M")} already exists in this department'
            )

        if 'shift_name' in data:
            data['shift_name'] = name
        return data
