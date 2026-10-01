from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
import datetime
from math import radians, sin, cos, sqrt, atan2

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import PermissionDenied, NotFound

from .models import Customuser, Attendance
from departments.models import Department
from designations.models import Designation
from shifts.models import Shift
from locations.models import Location

from .serializers import (
    OrganizationProfileSerializer,
    Signupserializer,
    Loginemployeeserializer,
    UserProfileSerializer,
    UserSerializer,
    AttendanceSerializer,
    EmployeeListSerializer
)

import traceback
import sys


# ============================================================
# GEO LOCATION HELPER
# ============================================================

GEOFENCE_RADIUS_METERS = 100


def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two GPS coordinates
    using the Haversine formula.

    Returns distance in meters.
    """

    earth_radius = 6371000  # Earth radius in meters

    lat1 = radians(float(lat1))
    lon1 = radians(float(lon1))
    lat2 = radians(float(lat2))
    lon2 = radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius * c


# ============================================================
# SIGNUP
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def signup_view(request):

    # NOTE: request.data is intentionally NOT logged (contains passwords)
    print("--- SIGNUP ATTEMPT START ---")
    print(f"Method: {request.method}")
    sys.stdout.flush()

    serializer = Signupserializer(data=request.data)

    # FIRST check validation
    if not serializer.is_valid():
        print("VALIDATION ERROR:", serializer.errors)
        return Response(serializer.errors, status=400)

    # THEN try saving
    try:
        employee = serializer.save()

        # Calculate the plain member password for the response
        phone_part = (
            employee.user.mobile_number[:5]
            if employee.user.mobile_number
            else ""
        )

        name_part = employee.first_name[:5]

        plain_member_password = f"{phone_part}{name_part}".lower()

        return Response({
            "message": "Employee created successfully",
            "member_password": plain_member_password,
            "temporary_password": getattr(
                employee,
                "temporary_password",
                None
            ),
        }, status=201)

    except Exception as e:
        print("SAVE ERROR:", str(e))
        traceback.print_exc()

        return Response(
            {"error": str(e)},
            status=500
        )


# ============================================================
# LIST USERS
# ============================================================

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
    sys.stdout.flush()

    # If the requester is an organization or they are requesting a list for an org
    if (
        request.user.is_organization
        or org_id
    ) and org_id not in [None, '', 'undefined', 'null']:

        try:
            # Filter by org_id and EXCLUDE the organization admin accounts themselves
            employees = Customuser.objects.filter(
                organisation_id=org_id
            ).exclude(
                user__is_organization=True
            )

            serializer = EmployeeListSerializer(
                employees,
                many=True
            )

            return Response(serializer.data)

        except (ValueError, TypeError):
            return Response(
                [],
                status=status.HTTP_200_OK
            )

    # Fallback for individual user profile if needed
    if not hasattr(request.user, 'employee'):
        return Response(
            {'error': 'Employee profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = UserProfileSerializer(
        request.user.employee
    )

    return Response({
        'user_type': request.user.user_type,
        'user_id': request.user.user_id,
        'profile': serializer.data
    })


# ============================================================
# EMPLOYEE LOGIN
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view_employee(request):

    serializer = Loginemployeeserializer(
        data=request.data
    )

    if serializer.is_valid():

        data = serializer.validated_data
        user = data['user']

        if user.is_organization:
            profile_data = OrganizationProfileSerializer(
                user
            ).data

        else:
            profile_data = UserProfileSerializer(
                user.employee
            ).data

        return Response({
            'message': 'Login successful',
            'access_token': data['access'],
            'refresh_token': data['refresh'],
            'user_type': user.user_type,
            'user_id': user.user_id,
            'org_id': data['org_id'],
            'user_role': data['user_role'],
            'profile': profile_data
        })

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


# ============================================================
# MEMBER LOGIN
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def member_login_view(request):

    from organisation.models import CustomUser as AuthUser
    from django.contrib.auth.hashers import check_password

    mobile_number = request.data.get('mobile_number')
    password = request.data.get('password')

    if not mobile_number:
        return Response(
            {"error": "Mobile number is required"},
            status=400
        )

    try:

        # Normalize mobile number to match DB format (10 digits)
        if hasattr(mobile_number, 'replace'):
            mobile_number = ''.join(
                filter(
                    str.isdigit,
                    str(mobile_number)
                )
            )[-10:]

        # Find the auth user first
        auth_user = AuthUser.objects.get(
            mobile_number=mobile_number
        )

        # Find the associated employee profile
        employee = Customuser.objects.get(
            user=auth_user
        )

        # Check member_password
        if not employee.member_password:
            return Response(
                {"error": "Member access not configured"},
                status=400
            )

        if (
            password == "FACE_BYPASS_PLACEHOLDER"
            and employee.is_member_registered
        ):
            # Face login bypass (for future face recognition)
            pass

        elif not check_password(
            password,
            employee.member_password
        ):

            # Calculate what it SHOULD be to show in error
            phone_part = (
                auth_user.mobile_number[:5]
                if auth_user.mobile_number
                else ""
            )

            name_part = employee.first_name[:5]

            expected_format = (
                f"{phone_part}{name_part}"
            ).lower()

            return Response({
                "error": "Invalid password",
                "detail": (
                    "Password should be: "
                    "first 5 digits of mobile + "
                    "first 5 letters of name "
                    f"(e.g. {expected_format})"
                )
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
            'profile': UserProfileSerializer(
                employee
            ).data
        })

    except AuthUser.DoesNotExist:
        return Response(
            {"error": "Member not found"},
            status=404
        )

    except Customuser.DoesNotExist:
        return Response(
            {"error": "Employee profile not found"},
            status=404
        )

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=500
        )


# ============================================================
# CHECK REGISTRATION STATUS
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def check_registration_status(request):

    from organisation.models import CustomUser as AuthUser

    mobile_number = request.data.get('mobile_number')

    print(f"DEBUG: check_registration_status received: {mobile_number}")

    if not mobile_number:
        return Response(
            {"error": "Mobile number required"},
            status=400
        )

    try:

        # Normalize mobile number to match DB format
        if hasattr(mobile_number, 'replace'):
            mobile_number = ''.join(
                filter(
                    str.isdigit,
                    str(mobile_number)
                )
            )[-10:]

        auth_user = AuthUser.objects.get(
            mobile_number=mobile_number
        )

        employee = Customuser.objects.get(
            user=auth_user
        )

        return Response({
            "is_registered": employee.is_member_registered,
            "exists": True
        })

    except AuthUser.DoesNotExist:
        return Response({
            "error": "Mobile number not found in our records.",
            "exists": False
        }, status=404)

    except Customuser.DoesNotExist:
        return Response({
            "error": (
                "This number belongs to an organization admin, "
                "not a member."
            ),
            "exists": False
        }, status=404)

    except Exception as e:
        print(f"ERROR in check_registration_status: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=500
        )


# ============================================================
# UPDATE USER
# ============================================================

@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_user(request, user_id):
    """Update employee details from the organization employee page."""

    current_org_id = request.user.pk

    print(
        f"DEBUG UPDATE: user_id={user_id}, "
        f"requester_pk={current_org_id}"
    )

    try:
        employee = Customuser.objects.filter(pk=user_id).first()

        if not employee:
            return Response(
                {"error": "Employee record not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Security: employee must belong to the logged-in organization.
        if (
            employee.organisation_id != current_org_id
            and not request.user.is_superuser
        ):
            return Response(
                {
                    "error": "Unauthorized",
                    "details": (
                        f"Employee belongs to org {employee.organisation_id}, "
                        f"but you are logged in as org {current_org_id}"
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # Copy request data so we can safely remove FK fields and org fields.
        data = request.data.copy()

        # Never allow the employee to be moved to another organization.
        data.pop("organisation", None)
        data.pop("org_id", None)

        # Frontend sends IDs for these foreign-key fields.
        # Resolve them manually to Django model instances.
        department_id = data.pop("department", None)
        designation_id = data.pop("designation", None)
        shift_id = data.pop("shift", None)
        location_id = data.pop("office_location", None)

        # Update normal fields through the existing serializer.
        serializer = Signupserializer(
            employee,
            data=data,
            partial=True
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer.save()

        # Department
        if department_id not in (None, "", "null", "undefined"):
            try:
                employee.department = Department.objects.get(
                    pk=int(department_id)
                )
            except (Department.DoesNotExist, TypeError, ValueError):
                return Response(
                    {"error": "Invalid department selected"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Designation
        if designation_id not in (None, "", "null", "undefined"):
            try:
                employee.designation = Designation.objects.get(
                    pk=int(designation_id)
                )
            except (Designation.DoesNotExist, TypeError, ValueError):
                return Response(
                    {"error": "Invalid designation selected"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Shift
        if shift_id not in (None, "", "null", "undefined"):
            try:
                employee.shift = Shift.objects.get(
                    pk=int(shift_id)
                )
            except (Shift.DoesNotExist, TypeError, ValueError):
                return Response(
                    {"error": "Invalid shift selected"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Office Location
        if location_id not in (None, "", "null", "undefined"):
            try:
                location = Location.objects.get(
                    pk=int(location_id)
                )
            except (Location.DoesNotExist, TypeError, ValueError):
                return Response(
                    {"error": "Invalid office location selected"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Location must belong to the same organization.
            if (
                location.org_id != employee.organisation_id
                and not request.user.is_superuser
            ):
                return Response(
                    {
                        "error": "Selected location does not belong to your organization"
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            employee.office_location = location

        # Save FK changes.
        employee.save()

        # Return updated employee (same serializer the list page uses).
        response_serializer = EmployeeListSerializer(employee)

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK
        )

    except Exception as e:
        print(f"ERROR UPDATE USER: {str(e)}")
        traceback.print_exc()

        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================
# DELETE USER
# ============================================================

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id):

    current_org_id = request.user.pk

    print(
        f"DEBUG DELETE: user_id={user_id}, "
        f"requester_pk={current_org_id}"
    )

    try:

        employee = Customuser.objects.filter(
            pk=user_id
        ).first()

        if not employee:
            return Response(
                {"error": "Employee record not found"},
                status=404
            )

        # Security check
        print(
            f"SECURITY CHECK: Employee's Org ID="
            f"{employee.organisation_id}, "
            f"Requester's User ID={request.user.pk}"
        )

        is_owner = (
            employee.organisation_id
            == request.user.pk
        )

        is_admin = (
            getattr(
                request.user,
                'is_organization',
                False
            )
            or request.user.is_superuser
        )

        if not (is_owner and is_admin) and not request.user.is_superuser:

            return Response({
                "error": "Unauthorized",
                "details": (
                    f"Ownership Check: {is_owner} "
                    f"(EmpOrg:{employee.organisation_id} "
                    f"vs ReqUser:{request.user.pk}), "
                    f"Admin Check: {is_admin}"
                )
            }, status=403)

        auth_user = employee.user

        if auth_user:
            auth_user.delete()
        else:
            employee.delete()

        # 200 (not 204) because we are returning a response body
        return Response(
            {"message": "Deleted successfully"},
            status=status.HTTP_200_OK
        )

    except Exception as e:

        return Response(
            {"error": str(e)},
            status=500
        )


# ============================================================
# EMPLOYEE DETAILS
# ============================================================

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def employee_details(request):

    user = request.user

    if user.is_organization:
        profile_data = OrganizationProfileSerializer(user).data

    else:
        try:
            profile_data = UserProfileSerializer(user.employee).data

        except AttributeError:
            return Response(
                {'error': 'Employee profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    return Response({
        'user_type': user.user_type,
        'user_id': user.org_id,
        'profile': profile_data
    })


# ============================================================
# ATTENDANCE STATUS
# ============================================================

def calculate_attendance_status(employee):
    """Helper function to calculate attendance status"""

    if not employee.shift:
        return 'On Time'

    # Use local time (settings.TIME_ZONE, e.g. Asia/Kolkata) so it
    # matches the shift start time, which is stored in local time.
    now = timezone.localtime(timezone.now())

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


# ============================================================
# MARK ATTENDANCE WITH GEO VALIDATION
# ============================================================

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_attendance(request):

    # Allow manual marking by organization admins
    employee_id = request.data.get('employee_id')

    print(
        "DEBUG AUTH USER:",
        request.user,
        "ID:",
        request.user.pk
    )

    # --------------------------------------------------------
    # FIND EMPLOYEE
    # --------------------------------------------------------

    if employee_id and request.user.is_organization:

        try:
            employee_profile = Customuser.objects.get(
                pk=employee_id,
                organisation=request.user
            )

        except Customuser.DoesNotExist:
            return Response(
                {'error': 'Employee not found in your organization'},
                status=status.HTTP_404_NOT_FOUND
            )

    else:

        try:
            employee_profile = request.user.employee

        except AttributeError:
            return Response(
                {'error': 'Employee profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    # --------------------------------------------------------
    # CHECK EXISTING OPEN ATTENDANCE
    # --------------------------------------------------------

    active_attendance = Attendance.objects.filter(
        employee=employee_profile,
        check_out__isnull=True
    ).first()

    if active_attendance:

        # Handle check-out
        active_attendance.check_out = timezone.now()
        active_attendance.save()

        serializer = AttendanceSerializer(
            active_attendance
        )

        return Response(
            serializer.data
        )

    # --------------------------------------------------------
    # END SESSION GUARD
    # If the frontend asked for a check-out but there is no open
    # check-in, do NOT create a new check-in.
    # --------------------------------------------------------

    if request.data.get('action') == 'checkout':
        return Response(
            {
                "error": "No active session",
                "detail": "No open check-in found. Please refresh and start the shift again."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    # --------------------------------------------------------
    # CHECK-IN
    # --------------------------------------------------------

    face_status = request.data.get(
        'face_status',
        'verified'
    )

    # Employee self-marking requires successful face verification
    if not employee_id and face_status != 'verified':
        return Response(
            {
                "error": "Face verification failed",
                "detail": "Attendance can be marked only after face verification."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    # Default location status
    location_status = 'inside'

    # --------------------------------------------------------
    # GEO VALIDATION
    #
    # Employee attendance:
    #   Get current GPS coordinates from frontend
    #   Compare with organization's saved location.
    #
    # Organization admin manual attendance:
    #   Keep existing manual behavior.
    # --------------------------------------------------------

    if not employee_id:

        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        # GPS coordinates are required for employee attendance
        if latitude is None or longitude is None:

            return Response(
                {
                    "error": "Current location is required",
                    "detail": "Latitude and longitude must be provided."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            # Employee's assigned office location (set by the org admin
            # in the Employees page). Fall back to the organization's
            # first saved location if none is assigned.
            office_location = employee_profile.office_location

            if not office_location:
                office_location = Location.objects.filter(
                    org_id=employee_profile.organisation_id
                ).first()

            if not office_location:

                return Response(
                    {
                        "error": "Office location not configured",
                        "detail": "Admin must add an office location and assign it to this employee."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Calculate distance between employee and office
            distance = calculate_distance(
                latitude,
                longitude,
                office_location.latitude,
                office_location.longitude
            )

            print(f"DEBUG GEO: Employee location=({latitude}, {longitude})")

            print(
                f"DEBUG GEO: Office location="
                f"({office_location.latitude}, "
                f"{office_location.longitude})"
            )

            print(f"DEBUG GEO: Distance={distance:.2f} meters")

            # Backend decides inside/outside.
            # Outside the office radius => attendance is NOT marked.
            if distance > GEOFENCE_RADIUS_METERS:
                return Response(
                    {
                        "error": "Location mismatch",
                        "detail": (
                            f"You are {int(distance)}m away from the office. "
                            f"Allowed radius: {GEOFENCE_RADIUS_METERS}m."
                        ),
                        "distance_meters": round(distance, 2),
                        "allowed_radius_meters": GEOFENCE_RADIUS_METERS,
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            location_status = 'inside'

        except (TypeError, ValueError):

            return Response(
                {"error": "Invalid location coordinates"},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:

            print(f"ERROR GEO VALIDATION: {str(e)}")

            return Response(
                {"error": "Unable to validate location"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    else:

        # Organization admin manual attendance
        location_status = request.data.get(
            'location_status',
            'inside'
        )

    # --------------------------------------------------------
    # ATTENDANCE STATUS
    # --------------------------------------------------------

    if face_status == 'failed':
        attendance_status = 'FAILED_VERIFICATION'

    elif location_status == 'outside':
        attendance_status = 'Late'

    else:
        attendance_status = calculate_attendance_status(
            employee_profile
        )

    # --------------------------------------------------------
    # CREATE ATTENDANCE
    # --------------------------------------------------------

    attendance = Attendance.objects.create(
        employee=employee_profile,
        check_in=timezone.now(),
        status=attendance_status,
        location_status=location_status,
        face_status=face_status
    )

    serializer = AttendanceSerializer(
        attendance
    )

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )


# ============================================================
# EMPLOYEE ATTENDANCE HISTORY
# ============================================================

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

    serializer = AttendanceSerializer(
        attendances,
        many=True
    )

    return Response(
        serializer.data
    )