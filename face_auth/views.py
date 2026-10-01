import base64
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from django.conf import settings
from django.core.files.base import ContentFile

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from organisation.models import CustomUser
from .models import EmployeeFaceData
from .serializers import FaceRegistrationSerializer, FaceDataSerializer


# =========================================================
# Initialize AWS Rekognition Client
# =========================================================

aws_config = Config(
    connect_timeout=10,
    read_timeout=20,
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
        print(f"Successfully synced face photo for {normalized}")

    except Exception as e:
        print(f"Failed to sync photo to employee profile: {str(e)}")


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
            print(
                f"Skipping comparison for "
                f"{other.user.mobile_number}: {str(e)}"
            )
            continue

    return False


# =========================================================
# CREATE AWS FACE LIVENESS SESSION
# =========================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def create_liveness_session(request):
    """Create an AWS Rekognition Face Liveness session"""

    try:
        start_time = time.perf_counter()

        response = rekognition.create_face_liveness_session()

        elapsed_time = time.perf_counter() - start_time
        print(f"LIVENESS CREATE AWS TIME: {elapsed_time:.2f} seconds")

        return Response({
            "session_id": response["SessionId"],
            "region": settings.AWS_DEFAULT_REGION
        })

    except ClientError as e:
        print(f"LIVENESS: AWS ClientError: {str(e)}")
        return Response(
            {"error": e.response["Error"]["Message"]},
            status=400
        )

    except Exception as e:
        print(f"LIVENESS: Unexpected error: {str(e)}")
        return Response(
            {"error": str(e)},
            status=500
        )


# =========================================================
# GET LIVENESS RESULT + FACE VERIFICATION
# =========================================================

@api_view(['POST'])
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
        print(f"LIVENESS RESULT AWS TIME: {liveness_elapsed_time:.2f} seconds")

        confidence = response.get("Confidence", 0)
        session_status = response.get("Status")
        reference_image = response.get("ReferenceImage")

        print(
            f"LIVENESS: Session={session_id}, "
            f"Status={session_status}, "
            f"Confidence={confidence}"
        )

        # =================================================
        # 2. CHECK LIVENESS STATUS
        # =================================================

        if session_status != "SUCCEEDED":

            total_elapsed_time = time.perf_counter() - total_start_time
            print(f"LIVENESS TOTAL TIME: {total_elapsed_time:.2f} seconds")

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

            print(f"FACE REGISTER: Starting registration for {normalized}")

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
            print(f"FACE REGISTRATION SUCCESS: {normalized}")
            print(f"REGISTRATION TOTAL TIME: {total_elapsed_time:.2f} seconds")

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
        print(f"FACE DB LOOKUP TIME: {db_elapsed_time:.4f} seconds")

        # =================================================
        # 6. DECODE REGISTERED FACE
        # =================================================

        decode_start_time = time.perf_counter()

        stored_image_bytes = base64.b64decode(
            face_record.face_image_base64
        )

        decode_elapsed_time = time.perf_counter() - decode_start_time
        print(f"FACE IMAGE DECODE TIME: {decode_elapsed_time:.4f} seconds")

        # =================================================
        # 7. COMPARE REGISTERED FACE WITH LIVENESS IMAGE
        # =================================================

        print(f"FACE VERIFY: Starting comparison for {normalized}...")

        compare_start_time = time.perf_counter()

        comparison = rekognition.compare_faces(
            SourceImage={"Bytes": stored_image_bytes},
            TargetImage={"Bytes": liveness_image_bytes},
            SimilarityThreshold=80
        )

        compare_elapsed_time = time.perf_counter() - compare_start_time
        print(f"FACE COMPARE AWS TIME: {compare_elapsed_time:.2f} seconds")

        # =================================================
        # 8. CHECK FACE MATCH
        # =================================================

        matches = comparison.get("FaceMatches", [])

        total_elapsed_time = time.perf_counter() - total_start_time
        print(
            f"LIVENESS + FACE VERIFY TOTAL TIME: "
            f"{total_elapsed_time:.2f} seconds"
        )

        if matches:
            similarity = matches[0]["Similarity"]
            print(f"FACE VERIFY: Match found! Similarity: {similarity}%")

            return Response({
                "verified": True,
                "status": session_status,
                "liveness_confidence": confidence,
                "similarity": similarity,
                "message": "Liveness and face verification successful."
            })

        print("FACE VERIFY: No match found")

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

        print(f"FACE VERIFY: No registered face found for {normalized}")

        total_elapsed_time = time.perf_counter() - total_start_time
        print(f"LIVENESS TOTAL TIME: {total_elapsed_time:.2f} seconds")

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

        print(f"LIVENESS/COMPARE: AWS ClientError: {str(e)}")

        total_elapsed_time = time.perf_counter() - total_start_time
        print(f"LIVENESS TOTAL TIME: {total_elapsed_time:.2f} seconds")

        return Response(
            {"error": e.response["Error"]["Message"]},
            status=400
        )

    # =====================================================
    # GENERAL ERROR
    # =====================================================

    except Exception as e:

        print(f"LIVENESS/COMPARE: Unexpected error: {str(e)}")

        total_elapsed_time = time.perf_counter() - total_start_time
        print(f"LIVENESS TOTAL TIME: {total_elapsed_time:.2f} seconds")

        return Response(
            {"error": str(e)},
            status=500
        )


# =========================================================
# CHECK FACE REGISTRATION STATUS
# =========================================================

@api_view(['POST'])
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

        print(f"DEBUG FACE: Starting comparison for {normalized}...")

        try:
            compare_start_time = time.perf_counter()

            aws_response = rekognition.compare_faces(
                SourceImage={"Bytes": stored_image_bytes},
                TargetImage={"Bytes": captured_image_bytes},
                SimilarityThreshold=80
            )

            compare_elapsed_time = time.perf_counter() - compare_start_time
            print(f"DEBUG FACE: AWS COMPARE TIME: {compare_elapsed_time:.2f} seconds")

        except ClientError as e:
            print(f"DEBUG FACE: AWS ClientError: {str(e)}")
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
            print(f"DEBUG FACE: Match found! Similarity: {similarity}%")

            return Response({
                "verified": True,
                "confidence": similarity,
                "similarity": similarity,
                "message": "Face verified successfully"
            })

        print("DEBUG FACE: No match found")

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
        print(f"DEBUG FACE: No record for {normalized}")
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
        print(f"DEBUG FACE: Unexpected error: {str(e)}")
        return Response(
            {"error": f"Internal Error: {str(e)}"},
            status=500
        )


# =========================================================
# GET FACE DETAILS
# =========================================================

@api_view(['GET'])
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