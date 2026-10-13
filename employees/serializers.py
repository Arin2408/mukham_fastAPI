import random
import string
from rest_framework import serializers
from .models import Customuser, Attendance
from departments.models import Department
from designations.models import Designation
from shifts.models import Shift
from locations.models import Location
from organisation.models import CustomUser as OrgUser
from rest_framework_simplejwt.tokens import RefreshToken

def normalize_mobile(mobile_number):
    return ''.join(filter(str.isdigit, str(mobile_number)))[-10:]

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
        fields = ['location_id', 'location_name', 'latitude', 'longitude']

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
    org_id = serializers.IntegerField(write_only=True, required=True)
    department = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    designation = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    shift = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    office_location = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    class Meta:
        model = Customuser
        fields = [
            'mobile_number', 'email', 'first_name', 'last_name',
            'department', 'designation', 'shift', 'office_location', 'organisation', 'org_id'
        ]
        extra_kwargs = {
            'organisation': {'required': False}
        }

    def validate_mobile_number(self, value):
        normalized = normalize_mobile(value)
        queryset = OrgUser.objects.filter(mobile_number=normalized)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.user.pk)
        if queryset.exists():
            raise serializers.ValidationError("A user with this mobile number already exists.")
        return normalized

    def validate_email(self, value):
        queryset = OrgUser.objects.filter(email=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.user.pk)
        if queryset.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        # Extract user data
        mobile_number = validated_data.pop('mobile_number')
        email = validated_data.pop('email')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        org_id = validated_data.pop('org_id', None)
        department_id = validated_data.pop('department', None)
        designation_id = validated_data.pop('designation', None)
        shift_id = validated_data.pop('shift', None)
        location_id = validated_data.pop('office_location', None)

        # Resolve Organization
        org_obj = None
        if org_id:
            try:
                org_obj = OrgUser.objects.get(org_id=org_id)
            except OrgUser.DoesNotExist:
                raise serializers.ValidationError({"org_id": "Invalid organization ID"})
        
        # Normalize mobile before lookup/creation
        mobile_number = normalize_mobile(mobile_number)
        user = OrgUser.objects.create_user(
            mobile_number=mobile_number,
            email=email,
            name=f"{first_name} {last_name}",
            is_organization=False
        )
        
        # Create employee with direct ID fields - this is the most robust way to avoid "expected a number" errors
        employee = Customuser.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            department_id=department_id,
            designation_id=designation_id,
            shift_id=shift_id,
            office_location_id=location_id,
            organisation=org_obj
        )
        
        # Add password to response data - GET the generated plain text password from the user object
        employee.temporary_password = getattr(user, 'temporary_password', None)
        return employee

    def update(self, instance, validated_data):
        # Extract user data
        mobile_number = validated_data.pop('mobile_number', None)
        email = validated_data.pop('email', None)
        first_name = validated_data.pop('first_name', None)
        last_name = validated_data.pop('last_name', None)
        org_id = validated_data.pop('org_id', None)

        # Update associated AuthUser
        user = instance.user
        if mobile_number:
            user.mobile_number = normalize_mobile(mobile_number)
        if email:
            user.email = email
        if first_name and last_name:
            user.name = f"{first_name} {last_name}"
        user.save()

        # Update profile fields
        if first_name:
            instance.first_name = first_name
        if last_name:
            instance.last_name = last_name
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['password'] = instance.temporary_password
        return data
class Loginemployeeserializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField()
    password = serializers.CharField()

    class Meta:
        model = OrgUser
        fields = ['mobile_number', 'password']

    def validate(self, attrs):
        mobile_number = attrs.get('mobile_number')
        password = attrs.get('password')

        # 🔍 Find user using normalized 10-digit mobile number
        user = OrgUser.objects.filter(
            mobile_number=normalize_mobile(mobile_number)
        ).first()

        if not user:
            raise serializers.ValidationError("Invalid mobile number")

        # 🔐 Check password
        if not user.check_password(password):
            raise serializers.ValidationError("Invalid password")

        # ✅ Generate tokens
        refresh = RefreshToken.for_user(user)

        # ✅ Return user data with tokens
        return {
            "user": user,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "org_id": user.org_id,
            "user_role": "organization" if user.is_organization else "employee"
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
        model = OrgUser
        fields = [
            'user_type', 'user_id', 'name', 'email', 
            'mobile_number', 'details'
        ]
    
    def get_user_id(self, obj):
        return obj.org_id
    
class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_id = serializers.IntegerField(source='employee.user.org_id', read_only=True)
    
    class Meta:
        model = Attendance
        fields = [
            'id',
            'employee',
            'employee_id',
            'employee_name',
            'check_in',
            'check_out',
            'status',
            'hours_worked',
            # Geofence / audit info
            'source',
            'location_status',
            'check_in_distance',
            'check_out_location_status',
            'check_out_distance'
        ]
        read_only_fields = [
            'status',
            'hours_worked',
            'source',
            'location_status',
            'check_in_distance',
            'check_out_location_status',
            'check_out_distance'
        ]
    
    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"

class CustomuserSerializer(serializers.ModelSerializer):
    attendances = AttendanceSerializer(many=True, read_only=True)
    
    class Meta:
        model = Customuser
        fields = [
            'user',
            'first_name',
            'last_name',
            'department',
            'designation',
            'shift',
            'office_location',
            'organisation',
            'attendances'
        ]
        depth = 1  # Shows nested relationships
class EmployeeListSerializer(serializers.ModelSerializer):
    employee_id = serializers.IntegerField(source='user.org_id', read_only=True)
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    department = serializers.PrimaryKeyRelatedField(read_only=True)
    designation = serializers.PrimaryKeyRelatedField(read_only=True)
    shift = serializers.PrimaryKeyRelatedField(read_only=True)
    office_location = serializers.PrimaryKeyRelatedField(read_only=True)
    designation_name = serializers.CharField(source='designation.details', read_only=True, default="N/A")
    department_name = serializers.CharField(source='department.details', read_only=True, default="N/A")
    shift_name = serializers.CharField(source='shift.shift_name', read_only=True, default="N/A")
    location_name = serializers.CharField(source='office_location.location_name', read_only=True, default="N/A")
    photo = serializers.SerializerMethodField()

    def get_photo(self, obj):
        """
        Return the employee photo URL, or None if the file is missing.
        Face images are no longer in the database, so a missing photo
        cannot be rebuilt here; FastAPI writes it at face enrolment.
        """
        if obj.photo and obj.photo.storage.exists(obj.photo.name):
            return obj.photo.url
        return None

    class Meta:
        model = Customuser
        fields = [
            'employee_id', 'first_name', 'last_name', 'mobile_number', 'email',
            'department', 'designation', 'shift', 'office_location',
            'designation_name', 'department_name', 'shift_name', 'location_name', 'photo'
        ]
