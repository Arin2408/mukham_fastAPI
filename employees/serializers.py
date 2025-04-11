import random
import string
from rest_framework import serializers
from .models import Customuser, Attendance
from departments.models import Department
from designations.models import Designation
from shifts.models import Shift
from locations.models import Location
from organisation.models import CustomUser
from rest_framework_simplejwt.tokens import RefreshToken
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
            'first_name', 'last_name', 'email',
            'department', 'designation', 'shift', 'office_location',
            'attendance_history'
        ]
        read_only_fields = ['id', 'mobile_number']

    def get_attendance_history(self, obj):
        attendances = Attendance.objects.filter(employee=obj).order_by('-check_in')[:30]
        return AttendanceSerializer(attendances, many=True).data

class UserSerializer(serializers.ModelSerializer):
    department = serializers.StringRelatedField()
    designation = serializers.StringRelatedField()
    shift = serializers.StringRelatedField()
    office_location = serializers.StringRelatedField()
    organisation = serializers.StringRelatedField(source='organisation.mobile_number')

    class Meta:
        model = Customuser
        fields = [
            'user',
            'mobile_number',
            'first_name',
            'last_name',
            'email',
            'department',
            'designation',
            'shift',
            'office_location',
            'organisation'
        ]
        read_only_fields = ['mobile_number', 'email']

class Signupserializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(write_only=True, required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    organisation_id = serializers.IntegerField(write_only=True, required=True)
    class Meta:
        model = Customuser
        fields = [
            'mobile_number', 'email', 'first_name', 'last_name',
            'department', 'designation', 'shift', 'office_location', 'organisation', 'organisation_id'
        ]
        extra_kwargs = {
            'organisation': {'required': False}
        }

    def create(self, validated_data):
        # Extract user data
        mobile_number = validated_data.pop('mobile_number')
        email = validated_data.pop('email')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        
        # Create user (password auto-generated in manager)
        user = CustomUser.objects.create_user(
            mobile_number=mobile_number,
            email=email,
            name=f"{first_name} {last_name}",
            is_organization=False
        )
        
        # Create employee
        employee = Customuser.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            **validated_data
        )
        
        # Add password to response data
        employee.temporary_password = user.password
        return employee

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['password'] = instance.temporary_password
        return data
class Loginemployeeserializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField()
    password = serializers.CharField()

    class Meta:
        model = CustomUser
        fields = ['mobile_number', 'password']
    def validate(self, attrs):
        mobile_number = attrs.get('mobile_number')
        password = attrs.get('password')
        
        try:
            user = CustomUser.objects.get(mobile_number=mobile_number)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError('Invalid mobile number')
        
        if user.password != password:  # Plain text comparison for now
            raise serializers.ValidationError('Invalid password')
        
        refresh = RefreshToken.for_user(user)
        
        return {
            'user': user,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'org_id': user.org_id,  # Add org_id to response
            'user_role': 'organization' if user.is_organization else 'employee'  # Add user_role
        }

class UserProfileSerializer(serializers.ModelSerializer):
    user_type = serializers.SerializerMethodField()  # Changed to SerializerMethodField
    user_id = serializers.SerializerMethodField()
    organisation = serializers.SerializerMethodField()  # To properly serialize organization
    
    class Meta:
        model = Customuser
        fields = [
            'user_type', 'user_id', 'first_name', 'last_name',
            'department', 'designation', 'shift', 'office_location', 'organisation'
        ]
        depth = 1  # To show nested relationships
    
    def get_user_type(self, obj):
        return obj.user.user_type  # Get from related CustomUser
    
    def get_user_id(self, obj):
        return obj.user.org_id  # Assuming org_id is the PK in CustomUser
    
    def get_organisation(self, obj):
        # Return minimal organization info
        return {
            'id': obj.organisation.org_id,
            'name': obj.organisation.name
        }

class OrganizationProfileSerializer(serializers.ModelSerializer):
    user_type = serializers.CharField()  # Removed redundant source
    user_id = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'user_type', 'user_id', 'name', 'email', 
            'mobile_number', 'details'
        ]
    
    def get_user_id(self, obj):
        return obj.org_id