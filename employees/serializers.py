from rest_framework import serializers
from .models import Customuser, Attendance
from departments.models import Department
from designations.models import Designation
from shifts.models import Shift
from locations.models import Location

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['department_id', 'details']

class DesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Designation
        fields = ['designation_id', 'details']

class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = ['shift_id', 'shift_name', 'shift_start_time', 'shift_end_time']

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['location_id', 'location_name']

class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attendance
        fields = ['id', 'check_in', 'check_out', 'status', 'hours_worked']
        read_only_fields = ['status', 'hours_worked']

class EmployeeDetailSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer()
    designation = DesignationSerializer()
    shift = ShiftSerializer()
    office_location = LocationSerializer()
    attendance_history = serializers.SerializerMethodField()

    class Meta:
        model = Customuser
        fields = [
            'id', 'first_name', 'last_name', 'email', 'mobile_number',
            'department', 'designation', 'shift', 'office_location',
            'attendance_history'
        ]

    def get_attendance_history(self, obj):
        attendances = Attendance.objects.filter(employee=obj).order_by('-check_in')[:30]
        return AttendanceSerializer(attendances, many=True).data

class Signupserializer(serializers.ModelSerializer):
    class Meta:
        model = Customuser
        fields = '__all__'

    def create(self, validated_data):
        return Customuser.objects.create(**validated_data)

class Loginserializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField()
    password = serializers.CharField()

    class Meta:
        model = Customuser
        fields = ['mobile_number', 'password']

