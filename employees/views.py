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
import sys

@api_view(['POST'])
@permission_classes([AllowAny])
def signup_view(request):
    import sys
    print("--- SIGNUP ATTEMPT START ---")
    print(f"Method: {request.method}")
    print(f"Data: {request.data}")
    sys.stdout.flush()

    serializer = Signupserializer(data=request.data)

    # ✅ FIRST check validation
    if not serializer.is_valid():
        print("VALIDATION ERROR:", serializer.errors)
        return Response(serializer.errors, status=400)

    # ✅ THEN try saving
    try:
        employee = serializer.save()
        
        # Calculate the plain member password for the response
        phone_part = employee.user.mobile_number[:5] if employee.user.mobile_number else ""
        name_part = employee.first_name[:5]
        plain_member_password = f"{phone_part}{name_part}".lower()
    
        return Response({
            "message": "Employee created successfully",
            "member_password": plain_member_password,
            "temporary_password": getattr(employee, "temporary_password", None),
        }, status=201)

    except Exception as e:
        print("SAVE ERROR:", str(e))
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_users(request):
    org_id = request.query_params.get('org_id')
    
    # Always prioritize the logged-in user's org_id if they are an organization
    if request.user.is_organization:
        org_id = request.user.org_id
    elif org_id in [None, '', 'undefined', 'null']:
        org_id = getattr(request.user, 'org_id', None)
    
    print(f"DEBUG LIST USERS (FIXED): Final Org ID used={org_id}")
    import sys
    sys.stdout.flush()

    # If the requester is an organization or they are requesting a list for an org
    if (request.user.is_organization or org_id) and org_id not in [None, '', 'undefined', 'null']:
        try:
            # Filter by org_id and EXCLUDE the organization admin accounts themselves
            employees = Customuser.objects.filter(
                organisation_id=org_id
            ).exclude(user__is_organization=True)
            
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

@api_view(['POST'])
@permission_classes([AllowAny])
def member_login_view(request):
    from organisation.models import CustomUser as AuthUser
    from django.contrib.auth.hashers import check_password
    
    mobile_number = request.data.get('mobile_number')
    password = request.data.get('password')

    if not mobile_number:
        return Response({"error": "Mobile number is required"}, status=400)

    try:
        # Normalize mobile number to match DB format (10 digits)
        if hasattr(mobile_number, 'replace'):
            mobile_number = ''.join(filter(str.isdigit, str(mobile_number)))[-10:]

        # Find the auth user first
        auth_user = AuthUser.objects.get(mobile_number=mobile_number)
        # Find the associated employee profile
        employee = Customuser.objects.get(user=auth_user)

        # Check member_password
        if not employee.member_password:
             return Response({"error": "Member access not configured"}, status=400)

        if password == "FACE_BYPASS_PLACEHOLDER" and employee.is_member_registered:
            # Face login bypass (for future face recognition)
            pass
        elif not check_password(password, employee.member_password):
            # Calculate what it SHOULD be to show in error (for debugging/admin help)
            phone_part = auth_user.mobile_number[:5] if auth_user.mobile_number else ""
            name_part = employee.first_name[:5]
            expected_format = f"{phone_part}{name_part}".lower()
            return Response({
                "error": "Invalid password",
                "detail": f"Password should be: first 5 digits of mobile + first 5 letters of name (e.g. {expected_format})"
            }, status=400)

        # Success logic
        if not employee.is_member_registered:
            employee.is_member_registered = True
            employee.save()
        
        # Generate tokens
        refresh = RefreshToken.for_user(auth_user)
        return Response({
            'message': 'Login successful',
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user_type': auth_user.user_type,
            'user_id': auth_user.user_id,
            'is_registered': employee.is_member_registered,
            'profile': UserProfileSerializer(employee).data
        })

    except AuthUser.DoesNotExist:
        return Response({"error": "Member not found"}, status=404)
    except Customuser.DoesNotExist:
        return Response({"error": "Employee profile not found"}, status=404)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return Response({"error": "Internal server error"}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
def check_registration_status(request):
    from organisation.models import CustomUser as AuthUser
    mobile_number = request.data.get('mobile_number')
    print(f"DEBUG: check_registration_status received: {mobile_number}")
    if not mobile_number:
        return Response({"error": "Mobile number required"}, status=400)
    
    try:
        # Normalize mobile number to match DB format (10 digits)
        if hasattr(mobile_number, 'replace'):
            mobile_number = ''.join(filter(str.isdigit, str(mobile_number)))[-10:]
            
        auth_user = AuthUser.objects.get(mobile_number=mobile_number)
        employee = Customuser.objects.get(user=auth_user)
        
        return Response({
            "is_registered": employee.is_member_registered,
            "exists": True
        })
    except AuthUser.DoesNotExist:
        return Response({"error": "Mobile number not found in our records.", "exists": False}, status=404)
    except Customuser.DoesNotExist:
        return Response({"error": "This number belongs to an organization admin, not a member.", "exists": False}, status=404)
    except Exception as e:
        print(f"ERROR in check_registration_status: {str(e)}")
        return Response({"error": "Internal server error"}, status=500)

@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_user(request, user_id):
    # Use request.user.pk as it's the most reliable ID for the logged-in admin
    current_org_id = request.user.pk
    print(f"DEBUG UPDATE: user_id={user_id}, requester_pk={current_org_id}")
    
    try:
        # If it's a superuser/org admin, they should have access
        employee = Customuser.objects.filter(pk=user_id).first()
        
        if not employee:
            return Response({"error": "Employee record not found"}, status=404)
            
        # Security check: Does this employee belong to the requester?
        if employee.organisation_id != current_org_id and not request.user.is_superuser:
            return Response({
                "error": "Unauthorized", 
                "details": f"Employee belongs to org {employee.organisation_id}, but you are logged in as org {current_org_id}"
            }, status=403)
        
        serializer = Signupserializer(employee, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id):
    current_org_id = request.user.pk
    print(f"DEBUG DELETE: user_id={user_id}, requester_pk={current_org_id}")
    
    try:
        employee = Customuser.objects.filter(pk=user_id).first()
        if not employee:
            return Response({"error": "Employee record not found"}, status=404)
            
        # Security check: Does this employee belong to the requester?
        print(f"SECURITY CHECK: Employee's Org ID={employee.organisation_id}, Requester's User ID={request.user.pk}")
        
        is_owner = (employee.organisation_id == request.user.pk)
        is_admin = getattr(request.user, 'is_organization', False) or request.user.is_superuser
        
        if not (is_owner and is_admin) and not request.user.is_superuser:
            return Response({
                "error": "Unauthorized",
                "details": f"Ownership Check: {is_owner} (EmpOrg:{employee.organisation_id} vs ReqUser:{request.user.pk}), Admin Check: {is_admin}"
            }, status=403)

        auth_user = employee.user
        if auth_user:
            auth_user.delete() # This will cascade and delete the employee record too
        else:
            employee.delete()
            
        return Response({"message": "Deleted successfully"}, status=204)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

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
    # Allow manual marking by organization admins
    employee_id = request.data.get('employee_id')
    print("DEBUG AUTH USER:", request.user, "ID:", request.user.pk)
    if employee_id and request.user.is_organization:
        try:
            employee_profile = Customuser.objects.get(pk=employee_id, organisation=request.user)
        except Customuser.DoesNotExist:
            return Response({'error': 'Employee not found in your organization'}, status=status.HTTP_404_NOT_FOUND)
    else:
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
    location_status = request.data.get('location_status', 'inside')
    face_status = request.data.get('face_status', 'verified')
    
    # Logic for status
    if face_status == 'failed':
        attendance_status = 'FAILED_VERIFICATION'
    elif location_status == 'outside':
        attendance_status = 'Late' # Marked as late if outside geofence as per requirements
    else:
        attendance_status = calculate_attendance_status(employee_profile)

    attendance = Attendance.objects.create(
        employee=employee_profile,
        check_in=timezone.now(),
        status=attendance_status,
        location_status=location_status,
        face_status=face_status
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