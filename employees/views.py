from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
import datetime
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Customuser, Attendance
from .serializers import OrganizationProfileSerializer, Signupserializer, Loginemployeeserializer, UserProfileSerializer, UserSerializer, AttendanceSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import PermissionDenied, NotFound

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def signup_view(request):
    request.data['org'] = request.user.org_id
    serializer = Signupserializer(data=request.data)
    if serializer.is_valid():
        employee = serializer.save()
        return Response({
            'message': 'Employee created successfully',
            'password': employee.temporary_password,
            'employee': UserProfileSerializer(employee).data
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_users(request):
    user = request.user
    if user.is_organization:
        serializer = OrganizationProfileSerializer(user)
    else:
        if not hasattr(user, 'employee'):
            return Response(
                {'error': 'Employee profile not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = UserProfileSerializer(user.employee)
    
    return Response({
        'user_type': user.user_type,
        'user_id': user.user_id,
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

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_attendance(request):
    user = request.user
    active_attendance = Attendance.objects.filter(
        employee=user, 
        check_out__isnull=True
    ).first()

    if active_attendance:
        # Handle check-out
        active_attendance.check_out = timezone.now()
        active_attendance.save()
        return Response(
            AttendanceSerializer(active_attendance).data,
            status=status.HTTP_200_OK
        )

    # Validate shift assignment
    if not user.shift:
        return Response(
            {"error": "No shift assigned to employee"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Create new attendance record with shift
    check_in_time = timezone.now()
    status = calculate_attendance_status(user.shift, check_in_time)
    
    attendance = Attendance.objects.create(
        employee=user,
        shift=user.shift,  # Directly use employee's assigned shift
        check_in=check_in_time,
        status=status
    )

    return Response(
        AttendanceSerializer(attendance).data,
        status=status.HTTP_201_CREATED
    )

def calculate_attendance_status(shift, check_in_time):
    """Calculate status based on shift timings"""
    shift_start = check_in_time.replace(
        hour=shift.shift_start_time.hour,
        minute=shift.shift_start_time.minute,
        second=0,
        microsecond=0
    )
    
    if check_in_time < shift_start:
        return 'Early'
    elif check_in_time > shift_start:
        return 'Late'
    return 'On Time'

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def employee_details(request):
    user = request.user
    if user.is_organization:
        serializer = OrganizationProfileSerializer(user)
    else:
        try:
            employee_profile = user.employee  # Will raise AttributeError if no employee profile
            serializer = UserProfileSerializer(employee_profile)
        except AttributeError:
            return Response(
                {'error': 'Employee profile not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    return Response({
        'user_type': user.user_type,
        'user_id': user.org_id,  # Changed to use org_id
        'profile': serializer.data
    })


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def attendance_history(request):
    """Get authenticated employee's attendance history"""
    attendances = Attendance.objects.filter(employee=request.user).select_related('shift')
    serializer = AttendanceSerializer(attendances, many=True)
    return Response(serializer.data)