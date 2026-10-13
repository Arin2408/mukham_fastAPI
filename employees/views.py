from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
import datetime
from math import radians, sin, cos, sqrt, atan2, isfinite

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

import logging

logger = logging.getLogger(__name__)


# ============================================================
# GEO LOCATION HELPER
# ============================================================

# The geofence radius is stored per office (Location.radius_meters).
# The GPS accuracy limit is settings.GEOFENCE_MAX_ACCURACY_METERS.

# Largest page allowed for ?limit= on attendance history
MAX_ATTENDANCE_PAGE_SIZE = 1000


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


class GeofenceError(Exception):
    """A check-in rejected by GPS / geofence validation."""

    def __init__(self, error, detail, http_status=status.HTTP_400_BAD_REQUEST, **extra):
        super().__init__(error)
        self.http_status = http_status
        self.payload = {"error": error, "detail": detail, **extra}


def parse_gps(data, required):
    """
    Read latitude / longitude / accuracy (metres, optional) from the request.

    Returns (latitude, longitude, accuracy) - accuracy may be None.
    Returns None when coordinates are missing and not required.
    Raises GeofenceError when they are required but missing, or invalid.
    """

    raw_latitude = data.get('latitude')
    raw_longitude = data.get('longitude')

    if raw_latitude in (None, '') or raw_longitude in (None, ''):
        if required:
            raise GeofenceError(
                "Current location is required",
                "Latitude and longitude must be provided."
            )
        return None

    try:
        latitude = float(raw_latitude)
        longitude = float(raw_longitude)
        raw_accuracy = data.get('accuracy')
        accuracy = None if raw_accuracy in (None, '') else float(raw_accuracy)

    except (TypeError, ValueError):
        raise GeofenceError(
            "Invalid location coordinates",
            "Latitude, longitude and accuracy must be numbers."
        )

    if (
        not (isfinite(latitude) and isfinite(longitude))
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or (latitude == 0 and longitude == 0)
    ):
        raise GeofenceError(
            "Invalid location coordinates",
            "The GPS position is not valid. Please enable location and try again."
        )

    if accuracy is not None and (not isfinite(accuracy) or accuracy < 0):
        raise GeofenceError(
            "Invalid location coordinates",
            "GPS accuracy must be a positive number of metres."
        )

    return latitude, longitude, accuracy


def find_office(employee, latitude, longitude):
    """
    Match a GPS position to the office the employee should be at.

    Uses the employee's assigned office. If none is assigned, picks the
    organisation's location the position is most inside of
    (smallest distance minus that location's radius).

    Returns (location, distance_in_meters), or (None, None) when the
    organisation has no locations.
    """

    if employee.office_location:
        candidates = [employee.office_location]
    else:
        candidates = Location.objects.filter(
            org_id=employee.organisation_id
        )

    best_location, best_distance = None, None

    for location in candidates:
        distance = calculate_distance(
            latitude,
            longitude,
            location.latitude,
            location.longitude
        )

        if (
            best_location is None
            or distance - location.radius_meters
            < best_distance - best_location.radius_meters
        ):
            best_location, best_distance = location, distance

    return best_location, best_distance


def record_check_out_location(attendance, employee, data):
    """
    Store the GPS sent with a check-out and flag it inside / outside.
    Check-out is never blocked: missing or unusable GPS is stored as 'unknown'.
    """

    try:
        gps = parse_gps(data, required=False)
    except GeofenceError:
        gps = None

    if not gps:
        attendance.check_out_location_status = 'unknown'
        return

    latitude, longitude, accuracy = gps

    attendance.check_out_latitude = latitude
    attendance.check_out_longitude = longitude
    attendance.check_out_accuracy = accuracy

    # Compare against the office used at check-in when known
    office = attendance.check_in_location

    if office:
        distance = calculate_distance(
            latitude,
            longitude,
            office.latitude,
            office.longitude
        )
    else:
        office, distance = find_office(employee, latitude, longitude)

    if not office:
        attendance.check_out_location_status = 'unknown'
        return

    attendance.check_out_distance = distance

    if (
        accuracy is not None
        and accuracy > settings.GEOFENCE_MAX_ACCURACY_METERS
    ):
        attendance.check_out_location_status = 'unknown'

    elif distance <= office.radius_meters:
        attendance.check_out_location_status = 'inside'

    else:
        attendance.check_out_location_status = 'outside'


# ============================================================
# QUERY HELPERS
# ============================================================

# Everything UserProfileSerializer / AttendanceSerializer / attendance
# status checks read from an employee, loaded in one JOIN query.
EMPLOYEE_RELATED = (
    "user",
    "organisation",
    "department",
    "designation",
    "shift",
    "office_location",
)


def get_employee_profile(user):
    """
    Load the employee profile for an auth user with all related rows.
    Raises Customuser.DoesNotExist if the user has no employee profile.
    """
    return Customuser.objects.select_related(*EMPLOYEE_RELATED).get(user=user)


# ============================================================
# SIGNUP
# ============================================================

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def signup_view(request):

    # NOTE: request.data is intentionally NOT logged (contains passwords)
    serializer = Signupserializer(data=request.data)

    # FIRST check validation
    if not serializer.is_valid():
        logger.info("Employee signup validation error: %s", serializer.errors)
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
        logger.exception("Employee signup failed")

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

    logger.debug("list_users: org_id=%s", org_id)

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
            ).select_related(
                "user",
                "department",
                "designation",
                "shift",
                "office_location",
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
    try:
        employee = get_employee_profile(request.user)

    except Customuser.DoesNotExist:
        return Response(
            {'error': 'Employee profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = UserProfileSerializer(
        employee
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
@authentication_classes([])
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
                get_employee_profile(user)
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
@authentication_classes([])
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
        employee = get_employee_profile(auth_user)

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
        logger.exception("Member login failed")
        return Response(
            {"error": "Internal server error"},
            status=500
        )


# ============================================================
# CHECK REGISTRATION STATUS
# ============================================================

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def check_registration_status(request):

    from organisation.models import CustomUser as AuthUser

    mobile_number = request.data.get('mobile_number')


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
        logger.exception("check_registration_status failed")
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

    logger.debug(
        "update_user: user_id=%s requester_pk=%s",
        user_id,
        current_org_id
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
        logger.exception("update_user failed for user_id=%s", user_id)

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

    logger.debug(
        "delete_user: user_id=%s requester_pk=%s",
        user_id,
        current_org_id
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
            profile_data = UserProfileSerializer(
                get_employee_profile(user)
            ).data

        except Customuser.DoesNotExist:
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

    today_start = now.replace(
        hour=employee.shift.shift_start_time.hour,
        minute=employee.shift.shift_start_time.minute,
        second=0,
        microsecond=0
    )

    # Use the shift start (yesterday / today / tomorrow) closest to now, so
    # night shifts that cross midnight (e.g. 20:00 -> 04:00) are judged correctly:
    # a 00:30 check-in for a 20:00 shift is Late, not Early.
    shift_start = min(
        (today_start + datetime.timedelta(days=d) for d in (-1, 0, 1)),
        key=lambda s: abs(now - s)
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

    # Manual (admin) marking skips GPS + face checks, so it is only allowed
    # for organisation admins. An employee sending employee_id is treated as
    # a normal self check-in and goes through all checks.
    is_manual = bool(employee_id) and request.user.is_organization

    # --------------------------------------------------------
    # FIND EMPLOYEE
    # --------------------------------------------------------

    if is_manual:

        try:
            employee_profile = Customuser.objects.select_related(
                *EMPLOYEE_RELATED
            ).get(
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
            employee_profile = get_employee_profile(request.user)

        except Customuser.DoesNotExist:
            return Response(
                {'error': 'Employee profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    # --------------------------------------------------------
    # CHECK EXISTING OPEN ATTENDANCE
    #
    # action = "checkin"  -> never checks out; a repeated check-in
    #                        returns the already-open record
    # action = "checkout" -> only checks out
    # no action           -> legacy toggle (check out if open, else check in)
    # --------------------------------------------------------

    action = request.data.get('action')

    with transaction.atomic():

        # Lock the open record so two parallel requests cannot both close it
        active_attendance = Attendance.objects.select_for_update().filter(
            employee=employee_profile,
            check_out__isnull=True
        ).first()

        if active_attendance and action != 'checkin':

            # Handle check-out (never blocked by location, only flagged)
            active_attendance.check_out = timezone.now()

            if is_manual:
                active_attendance.check_out_location_status = 'manual'
            else:
                record_check_out_location(
                    active_attendance,
                    employee_profile,
                    request.data
                )

            active_attendance.save()

    if active_attendance:

        # Reuse the already-loaded employee for serialization
        active_attendance.employee = employee_profile

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

    if action == 'checkout':
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

    if is_manual:

        # Organisation admin manual attendance: no GPS / face check.
        # Recorded as a manual entry; location/face values sent by the
        # client are not trusted.
        face_status = 'skipped'
        location_status = 'manual'
        gps = None
        office_location, distance = None, None

    else:

        face_status = request.data.get(
            'face_status',
            'verified'
        )

        # Employee self-marking requires successful face verification
        if face_status != 'verified':
            return Response(
                {
                    "error": "Face verification failed",
                    "detail": "Attendance can be marked only after face verification."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ----------------------------------------------------
        # GEO VALIDATION (server is the final authority)
        # ----------------------------------------------------

        try:
            gps = parse_gps(request.data, required=True)
            latitude, longitude, accuracy = gps

            max_accuracy = settings.GEOFENCE_MAX_ACCURACY_METERS

            if accuracy is not None and accuracy > max_accuracy:
                raise GeofenceError(
                    "GPS accuracy too low",
                    (
                        f"Your location is only accurate to about {int(accuracy)}m "
                        f"(needs {max_accuracy}m or better). Turn on precise "
                        "location, move near a window or outdoors, and try again."
                    ),
                    accuracy_meters=round(accuracy, 1),
                    max_accuracy_meters=max_accuracy,
                )

            office_location, distance = find_office(
                employee_profile,
                latitude,
                longitude
            )

            if not office_location:
                raise GeofenceError(
                    "Office location not configured",
                    "Admin must add an office location for your organisation."
                )

            logger.debug(
                "Geofence: employee=(%s, %s) +/-%sm office=%s (%s, %s) r=%sm distance=%.2fm",
                latitude,
                longitude,
                accuracy,
                office_location.pk,
                office_location.latitude,
                office_location.longitude,
                office_location.radius_meters,
                distance
            )

            # Outside the office radius => attendance is NOT marked.
            if distance > office_location.radius_meters:
                raise GeofenceError(
                    "Location mismatch",
                    (
                        f"You are {int(distance)}m away from "
                        f"{office_location.location_name}. "
                        f"Allowed radius: {office_location.radius_meters}m."
                    ),
                    http_status=status.HTTP_403_FORBIDDEN,
                    distance_meters=round(distance, 2),
                    allowed_radius_meters=office_location.radius_meters,
                    office_location=office_location.location_name,
                )

        except GeofenceError as e:
            return Response(e.payload, status=e.http_status)

        location_status = 'inside'

    # --------------------------------------------------------
    # ATTENDANCE STATUS
    # --------------------------------------------------------

    attendance_status = calculate_attendance_status(
        employee_profile
    )

    # --------------------------------------------------------
    # CREATE ATTENDANCE
    # --------------------------------------------------------

    try:
        with transaction.atomic():
            attendance = Attendance.objects.create(
                employee=employee_profile,
                check_in=timezone.now(),
                status=attendance_status,
                location_status=location_status,
                face_status=face_status,
                source='manual' if is_manual else 'self',
                marked_by=request.user if is_manual else None,
                check_in_latitude=gps[0] if gps else None,
                check_in_longitude=gps[1] if gps else None,
                check_in_accuracy=gps[2] if gps else None,
                check_in_distance=distance,
                check_in_location=office_location,
            )

    except IntegrityError:

        # A parallel request already checked this employee in
        # (one_open_attendance_per_employee constraint) - return that record.
        attendance = Attendance.objects.filter(
            employee=employee_profile,
            check_out__isnull=True
        ).first()

        if not attendance:
            raise

        attendance.employee = employee_profile

        return Response(
            AttendanceSerializer(attendance).data
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
        # (employee PK is the auth user's PK, so no extra lookup is needed)
        attendances = Attendance.objects.filter(
            employee_id=request.user.pk
        )

    # AttendanceSerializer reads employee name and employee.user.org_id
    attendances = attendances.select_related(
        "employee",
        "employee__user"
    )

    # --------------------------------------------------------
    # OPTIONAL FILTERS / PAGING
    # ?from=YYYY-MM-DD&to=YYYY-MM-DD  (local dates, inclusive)
    # ?limit=N&offset=M               (newest first)
    # Without these params the full history is returned, as before.
    # --------------------------------------------------------

    params = request.query_params

    try:
        if params.get('from'):
            from_date = parse_date(params['from'])
            attendances = attendances.filter(
                check_in__gte=timezone.make_aware(
                    datetime.datetime.combine(from_date, datetime.time.min)
                )
            )

        if params.get('to'):
            to_date = parse_date(params['to'])
            attendances = attendances.filter(
                check_in__lt=timezone.make_aware(
                    datetime.datetime.combine(
                        to_date + datetime.timedelta(days=1),
                        datetime.time.min
                    )
                )
            )

        offset = int(params.get('offset', 0))
        limit = params.get('limit')

        if offset < 0:
            raise ValueError

        if limit is not None:
            limit = int(limit)

            if not 1 <= limit <= MAX_ATTENDANCE_PAGE_SIZE:
                raise ValueError

            attendances = attendances[offset:offset + limit]

        elif offset:
            attendances = attendances[offset:]

    except (TypeError, ValueError):
        return Response(
            {
                "error": "Invalid query parameters",
                "detail": (
                    "from/to must be YYYY-MM-DD, offset >= 0, "
                    f"limit between 1 and {MAX_ATTENDANCE_PAGE_SIZE}."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = AttendanceSerializer(
        attendances,
        many=True
    )

    return Response(
        serializer.data
    )