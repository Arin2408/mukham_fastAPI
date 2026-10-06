import base64
import logging
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from django.conf import settings
from django.core.files.base import ContentFile

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from organisation.models import CustomUser
from .models import EmployeeFaceData
from .serializers import FaceRegistrationSerializer, FaceDataSerializer

logger = logging.getLogger(__name__)


# =========================================================
# Initialize AWS Rekognition Client
# =========================================================

# Fail fast: a stuck AWS call should not hold a server worker for long.
# Worst case per call is roughly (connect + read) x total_max_attempts.
aws_config = Config(
    connect_timeout=3,
    read_timeout=8,
    retries={
        "total_max_attempts": 2,
        "mode": "standard"
    },
    tcp_keepalive=True
)

rekognition = boto3.client(
    "rekognition",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_DEFAULT_REGION,
    config=aws_config
)


# =========================================================
# Helpers
# =========================================================

def normalize_mobile(mobile_number):
    """Keep only digits and return the last 10."""
    return ''.join(filter(str.isdigit, str(mobile_number)))[-10:]


def sync_employee_photo(normalized, image_bytes):
    """Keep employee profile photo in sync with the registered face."""
    try:
        from employees.models import Customuser as EmployeeRecord

        employee = EmployeeRecord.objects.get(
            user__mobile_number=normalized
        )
        employee.photo.save(
            f"face_{normalized}.jpg",
            ContentFile(image_bytes),
            save=True
        )
        logger.debug("Synced face photo for %s", normalized)

    except Exception as e:
        logger.warning("Failed to sync face photo to employee profile for %s: %s", normalized, e)


def is_duplicate_face(normalized, image_bytes):
    """
    Return True if this face already matches a face registered
    to ANOTHER employee.
    """
    other_faces = EmployeeFaceData.objects.exclude(
        user__mobile_number=normalized
    )

    for other in other_faces:
        try:
            stored_bytes = base64.b64decode(other.face_image_base64)

            comparison = rekognition.compare_faces(
                SourceImage={"Bytes": stored_bytes},
                TargetImage={"Bytes": image_bytes},
                SimilarityThreshold=90
            )

            if comparison.get("FaceMatches"):
                return True

        except Exception as e:
            logger.warning(
                "Duplicate-face check: skipping comparison for %s: %s",
                other.user_id,
                e
            )
            continue

    return False


# =========================================================
# CREATE AWS FACE LIVENESS SESSION
# =========================================================

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def create_liveness_session(request):
    """Create an AWS Rekognition Face Liveness session"""

    try:
        start_time = time.perf_counter()

        response = rekognition.create_face_liveness_session()

        elapsed_time = time.perf_counter() - start_time
        logger.debug("Liveness create AWS time: %.2fs", elapsed_time)

        return Response({
            "session_id": response["SessionId"],
            "region": settings.AWS_DEFAULT_REGION
        })

    except ClientError as e:
        logger.warning("Liveness create: AWS ClientError: %s", e)
        return Response(
            {"error": e.response["Error"]["Message"]},
            status=400
        )

    except Exception as e:
        logger.exception("Liveness create failed")
        return Response(
            {"error": str(e)},
            status=500
        )


# =========================================================
# GET LIVENESS RESULT + FACE VERIFICATION
# =========================================================

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def get_liveness_result(request):
    """
    Get AWS Rekognition Face Liveness result and compare the
    AWS liveness reference image with the employee's registered face.

    mode = "register" -> save the liveness image as the employee's face
    mode = "verify"   -> compare the liveness image with the stored face
    """

    total_start_time = time.perf_counter()

    # -----------------------------------------------------
    # Get + validate request data
    # -----------------------------------------------------

    session_id = request.data.get('session_id')
    mobile_number = request.data.get('mobile_number')
    mode = request.data.get('mode', 'verify')

    if not session_id:
        return Response({"error": "session_id is required"}, status=400)

    if not mobile_number:
        return Response({"error": "mobile_number is required"}, status=400)

    if mode not in ("register", "verify"):
        return Response(
            {"error": "mode must be 'register' or 'verify'"},
            status=400
        )

    normalized = normalize_mobile(mobile_number)

    try:

        # =================================================
        # 1. GET AWS LIVENESS RESULT
        # =================================================

        liveness_start_time = time.perf_counter()

        response = rekognition.get_face_liveness_session_results(
            SessionId=session_id
        )

        liveness_elapsed_time = time.perf_counter() - liveness_start_time
        logger.debug("Liveness result AWS time: %.2fs", liveness_elapsed_time)

        confidence = response.get("Confidence", 0)
        session_status = response.get("Status")
        reference_image = response.get("ReferenceImage")

        logger.info(
            "Liveness: session=%s status=%s confidence=%s",
            session_id,
            session_status,
            confidence
        )

        # =================================================
        # 2. CHECK LIVENESS STATUS
        # =================================================

        if session_status != "SUCCEEDED":

            total_elapsed_time = time.perf_counter() - total_start_time
            logger.debug("Liveness total time: %.2fs", total_elapsed_time)

            return Response(
                {
                    "verified": False,
                    "status": session_status,
                    "confidence": confidence,
                    "message": "Face liveness verification failed."
                },
                status=400
            )

        # =================================================
        # 3. GET AWS LIVENESS REFERENCE IMAGE
        # =================================================

        if not reference_image:
            return Response(
                {
                    "verified": False,
                    "message": "Liveness reference image not available."
                },
                status=400
            )

        if "Bytes" not in reference_image:
            return Response(
                {
                    "verified": False,
                    "message": "Liveness reference image bytes not available."
                },
                status=400
            )

        liveness_image_bytes = reference_image["Bytes"]

        # =================================================
        # 4. NEW USER - REGISTER FACE
        # =================================================

        if mode == "register":

            if not CustomUser.objects.filter(
                mobile_number=normalized
            ).exists():
                return Response(
                    {
                        "registered": False,
                        "verified": False,
                        "message": "Employee not found."
                    },
                    status=404
                )

            if EmployeeFaceData.objects.filter(
                user__mobile_number=normalized
            ).exists():
                return Response(
                    {
                        "registered": False,
                        "verified": False,
                        "message": "Face is already registered for this employee."
                    },
                    status=400
                )

            # Prevent the same face from being registered to another employee
            if is_duplicate_face(normalized, liveness_image_bytes):
                return Response(
                    {
                        "registered": False,
                        "verified": False,
                        "status": session_status,
                        "confidence": confidence,
                        "error": (
                            "This face is already registered "
                            "to another employee account."
                        ),
                        "code": "DUPLICATE_FACE"
                    },
                    status=400
                )

            new_face_base64 = base64.b64encode(
                liveness_image_bytes
            ).decode("utf-8")

            serializer = FaceRegistrationSerializer(
                data={
                    "mobile_number": normalized,
                    "face_image_base64": new_face_base64
                }
            )

            if not serializer.is_valid():
                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer.save()

            sync_employee_photo(normalized, liveness_image_bytes)

            total_elapsed_time = time.perf_counter() - total_start_time
            logger.info(
                "Face registered for %s in %.2fs",
                normalized,
                total_elapsed_time
            )

            return Response(
                {
                    "registered": True,
                    "verified": True,
                    "status": session_status,
                    "confidence": confidence,
                    "message": "Face registered successfully."
                },
                status=status.HTTP_201_CREATED
            )

        # =================================================
        # 5. EXISTING USER - GET REGISTERED FACE
        #    (only needed for verify mode, so it is fetched
        #     here and NOT before the register block)
        # =================================================

        db_start_time = time.perf_counter()

        face_record = EmployeeFaceData.objects.get(
            user__mobile_number=normalized
        )

        db_elapsed_time = time.perf_counter() - db_start_time
        logger.debug("Face DB lookup time: %.4fs", db_elapsed_time)

        # =================================================
        # 6. DECODE REGISTERED FACE
        # =================================================

        decode_start_time = time.perf_counter()

        stored_image_bytes = base64.b64decode(
            face_record.face_image_base64
        )

        decode_elapsed_time = time.perf_counter() - decode_start_time
        logger.debug("Face image decode time: %.4fs", decode_elapsed_time)

        # =================================================
        # 7. COMPARE REGISTERED FACE WITH LIVENESS IMAGE
        # =================================================

        compare_start_time = time.perf_counter()

        comparison = rekognition.compare_faces(
            SourceImage={"Bytes": stored_image_bytes},
            TargetImage={"Bytes": liveness_image_bytes},
            SimilarityThreshold=80
        )

        compare_elapsed_time = time.perf_counter() - compare_start_time
        logger.debug("Face compare AWS time: %.2fs", compare_elapsed_time)

        # =================================================
        # 8. CHECK FACE MATCH
        # =================================================

        matches = comparison.get("FaceMatches", [])

        total_elapsed_time = time.perf_counter() - total_start_time
        logger.debug(
            "Liveness + face verify total time: %.2fs",
            total_elapsed_time
        )

        if matches:
            similarity = matches[0]["Similarity"]
            logger.info("Face verify: match for %s (similarity %.1f%%)", normalized, similarity)

            return Response({
                "verified": True,
                "status": session_status,
                "liveness_confidence": confidence,
                "similarity": similarity,
                "message": "Liveness and face verification successful."
            })

        logger.info("Face verify: no match for %s", normalized)

        return Response(
            {
                "verified": False,
                "status": session_status,
                "liveness_confidence": confidence,
                "similarity": 0,
                "message": "Face does not match the registered employee."
            },
            status=400
        )

    # =====================================================
    # EMPLOYEE FACE NOT FOUND
    # =====================================================

    except EmployeeFaceData.DoesNotExist:

        logger.info("Face verify: no registered face for %s", normalized)

        return Response(
            {
                "verified": False,
                "message": "No registered face found for this employee."
            },
            status=404
        )

    # =====================================================
    # AWS ERROR
    # =====================================================

    except ClientError as e:

        logger.warning("Liveness/compare: AWS ClientError: %s", e)

        return Response(
            {"error": e.response["Error"]["Message"]},
            status=400
        )

    # =====================================================
    # GENERAL ERROR
    # =====================================================

    except Exception as e:

        logger.exception("Liveness/compare failed")

        return Response(
            {"error": str(e)},
            status=500
        )


# =========================================================
# CHECK FACE REGISTRATION STATUS
# =========================================================

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def check_face_status(request):
    """Check if a mobile number has a face registered"""

    mobile_number = request.data.get('mobile_number')

    if not mobile_number:
        return Response({"error": "Mobile number required"}, status=400)

    normalized = normalize_mobile(mobile_number)

    if not CustomUser.objects.filter(mobile_number=normalized).exists():
        return Response(
            {
                "error": "User not found in records",
                "exists": False
            },
            status=404
        )

    face_exists = EmployeeFaceData.objects.filter(
        user__mobile_number=normalized
    ).exists()

    return Response({
        "mobile_number": normalized,
        "is_face_registered": face_exists,
        "exists": True
    })


# =========================================================
# REGISTER FACE (DIRECT IMAGE UPLOAD)
# =========================================================

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def register_face(request):
    """Register face data for an employee, ensuring no duplicates exist."""

    mobile_number = request.data.get('mobile_number')
    new_face_base64 = request.data.get('face_image_base64')

    if not mobile_number or not new_face_base64:
        return Response(
            {"error": "Mobile number and image data required"},
            status=400
        )

    normalized_new = normalize_mobile(mobile_number)

    try:
        new_face_bytes = base64.b64decode(new_face_base64)
    except Exception:
        return Response({"error": "Invalid image data"}, status=400)

    # Security check: prevent duplicate faces
    if is_duplicate_face(normalized_new, new_face_bytes):
        return Response(
            {
                "error": (
                    "This face is already registered "
                    "to another employee account."
                ),
                "code": "DUPLICATE_FACE"
            },
            status=400
        )

    serializer = FaceRegistrationSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()

        sync_employee_photo(normalized_new, new_face_bytes)

        return Response(
            {"message": "Face data registered successfully"},
            status=status.HTTP_201_CREATED
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =========================================================
# OLD / DIRECT FACE VERIFICATION
# =========================================================

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def verify_face(request):
    """Verify live face against stored reference image"""

    mobile_number = request.data.get('mobile_number')
    captured_image_base64 = request.data.get('face_image_base64')

    if not mobile_number or not captured_image_base64:
        return Response(
            {"error": "Mobile number and image data required"},
            status=400
        )

    normalized = normalize_mobile(mobile_number)

    try:
        face_record = EmployeeFaceData.objects.get(
            user__mobile_number=normalized
        )

        stored_image_bytes = base64.b64decode(face_record.face_image_base64)
        captured_image_bytes = base64.b64decode(captured_image_base64)

        try:
            compare_start_time = time.perf_counter()

            aws_response = rekognition.compare_faces(
                SourceImage={"Bytes": stored_image_bytes},
                TargetImage={"Bytes": captured_image_bytes},
                SimilarityThreshold=80
            )

            compare_elapsed_time = time.perf_counter() - compare_start_time
            logger.debug("Face compare AWS time: %.2fs", compare_elapsed_time)

        except ClientError as e:
            logger.warning("Face verify: AWS ClientError: %s", e)
            return Response(
                {
                    "error": (
                        f"Face verification failed: "
                        f"{e.response['Error']['Message']}"
                    )
                },
                status=400
            )

        matches = aws_response.get("FaceMatches", [])

        if matches:
            similarity = matches[0]["Similarity"]
            logger.info("Face verify: match for %s (similarity %.1f%%)", normalized, similarity)

            return Response({
                "verified": True,
                "confidence": similarity,
                "similarity": similarity,
                "message": "Face verified successfully"
            })

        logger.info("Face verify: no match for %s", normalized)

        return Response(
            {
                "verified": False,
                "confidence": 0,
                "message": (
                    "Face verification failed. "
                    "No match found. "
                    "Please look directly at the camera."
                )
            },
            status=400
        )

    except EmployeeFaceData.DoesNotExist:
        logger.info("Face verify: no registered face for %s", normalized)
        return Response(
            {
                "error": (
                    "No reference face image found. "
                    "Please register first."
                )
            },
            status=404
        )

    except Exception as e:
        logger.exception("Face verify failed")
        return Response(
            {"error": f"Internal Error: {str(e)}"},
            status=500
        )


# =========================================================
# GET FACE DETAILS
# =========================================================

@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def get_face_details(request, mobile_number):
    """Retrieve face data for a specific mobile number"""

    normalized = normalize_mobile(mobile_number)

    try:
        face_data = EmployeeFaceData.objects.get(
            user__mobile_number=normalized
        )
        serializer = FaceDataSerializer(face_data)
        return Response(serializer.data)

    except EmployeeFaceData.DoesNotExist:
        return Response(
            {"error": "Face data not found"},
            status=status.HTTP_404_NOT_FOUND
        )