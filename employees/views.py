from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
import datetime
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Customuser, Attendance
from .serializers import OrganizationProfileSerializer, Signupserializer, Loginemployeeserializer, UserProfileSerializer, UserSerializer, AttendanceSerializer, EmployeeListSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import PermissionDenied, NotFound
import traceback
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

import traceback
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

@api_view(['POST'])
@permission_classes([AllowAny])
def signup_view(request):
    print("🔥 Signup API HIT")
    print("📦 Data:", request.data)

    serializer = Signupserializer(data=request.data)

    # ✅ FIRST check validation
    if not serializer.is_valid():
        print("❌ VALIDATION ERROR:", serializer.errors)
        return Response(serializer.errors, status=400)

    # ✅ THEN try saving
    try:
        employee = serializer.save()
        return Response({
            "message": "Employee created successfully",
            "password": getattr(employee, "temporary_password", None),
        }, status=201)

    except Exception as e:
        print("💥 SAVE ERROR:", str(e))
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_users(request):
    org_id = request.query_params.get('org_id')
    
    # Handle cases where org_id might be 'undefined' or 'null' literals from frontend
    if org_id in [None, '', 'undefined', 'null']:
        org_id = getattr(request.user, 'org_id', None)

    # If the requester is an organization or they are requesting a list for an org
    if (request.user.is_organization or org_id) and org_id not in [None, '', 'undefined', 'null']:
        try:
            employees = Customuser.objects.filter(organisation_id=org_id)
            serializer = EmployeeListSerializer(employees, many=True)
            return Response(serializer.data)
        except (ValueError, TypeError):
            return Response([], status=status.HTTP_200_OK) # Return empty list on invalid ID
    
    # Fallback for individual user profile if needed
    if not hasattr(request.user, 'employee'):
        return Response(
            {'error': 'Employee profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    serializer = UserProfileSerializer(request.user.employee)
    return Response({
        'user_type': request.user.user_type,
        'user_id': request.user.user_id,
        'profile': serializer.data
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view_employee(request):
    serializer = Loginemployeeserializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data
        user = data['user']
        
        if user.is_organization:
            profile_data = OrganizationProfileSerializer(user).data
        else:
            profile_data = UserProfileSerializer(user.employee).data
        
        return Response({
            'message': 'Login successful',
            'access_token': data['access'],
            'refresh_token': data['refresh'],
            'user_type': user.user_type,
            'user_id': user.user_id,
            'org_id': data['org_id'],  # Include org_id
            'user_role': data['user_role'],  # Include user_role
            'profile': profile_data
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_user(request, user_id):
    try:
        user = Customuser.objects.get(id=user_id, organisation=request.user.org_id)
    except Customuser.DoesNotExist:
        return Response({"error": "User not found or not accessible"}, status=status.HTTP_404_NOT_FOUND)

    serializer = Signupserializer(user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id):
    try:
        user = Customuser.objects.get(id=user_id, organisation=request.user.org_id)
    except Customuser.DoesNotExist:
        return Response({"error": "User not found or not accessible"}, status=status.HTTP_404_NOT_FOUND)

    user.delete()
    return Response({"message": "User deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def employee_details(request):
    user = request.user
    if user.is_organization:
        serializer = OrganizationProfileSerializer(user)
    else:
        try:
            employee_profile = user.employee  
            serializer = UserProfileSerializer(employee_profile)
        except AttributeError:
            return Response(
                {'error': 'Employee profile not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    return Response({
        'user_type': user.user_type,
        'user_id': user.org_id,  
        'profile': serializer.data
    })


def calculate_attendance_status(employee):
    """Helper function to calculate attendance status"""
    if not employee.shift:
        return 'On Time'  # Default if no shift assigned
    
    now = timezone.now()
    shift_start = now.replace(
        hour=employee.shift.shift_start_time.hour,
        minute=employee.shift.shift_start_time.minute,
        second=0,
        microsecond=0
    )
    
    if now < shift_start - datetime.timedelta(minutes=15):
        return 'Early'
    elif now > shift_start + datetime.timedelta(minutes=15):
        return 'Late'
    return 'On Time'

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_attendance(request):
    try:
        employee_profile = request.user.employee
    except AttributeError:
        return Response(
            {'error': 'Employee profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check for existing open attendance
    active_attendance = Attendance.objects.filter(
        employee=employee_profile,
        check_out__isnull=True
    ).first()
    
    if active_attendance:
        # Handle check-out
        active_attendance.check_out = timezone.now()
        active_attendance.save()
        serializer = AttendanceSerializer(active_attendance)
        return Response(serializer.data)
    
    # Handle check-in
    attendance = Attendance.objects.create(
        employee=employee_profile,
        check_in=timezone.now(),
        status=calculate_attendance_status(employee_profile)  # Fixed: Using standalone function
    )
    
    serializer = AttendanceSerializer(attendance)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def employee_attendance(request, employee_id=None):
    if request.user.is_organization:
        # Organization viewing employee attendance
        if employee_id:
            attendances = Attendance.objects.filter(
                employee__id=employee_id,
                employee__organisation=request.user
            )
        else:
            attendances = Attendance.objects.filter(
                employee__organisation=request.user
            )
    else:
        # Employee viewing their own attendance
        attendances = Attendance.objects.filter(
            employee=request.user.employee
        )
    
    serializer = AttendanceSerializer(attendances, many=True)
    return Response(serializer.data)