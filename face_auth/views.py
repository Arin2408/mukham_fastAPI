from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import EmployeeFaceData
from .serializers import FaceRegistrationSerializer, FaceDataSerializer

from organisation.models import CustomUser

from django.conf import settings

import boto3
import base64
import time

from botocore.exceptions import ClientError


# =========================================================
# Initialize AWS Rekognition Client
# =========================================================

from botocore.config import Config

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
# CREATE AWS FACE LIVENESS SESSION
# =========================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def create_liveness_session(request):
    """Create an AWS Rekognition Face Liveness session"""

    try:
        # -----------------------------------------------------
        # Measure AWS Create Liveness Session time
        # -----------------------------------------------------

        start_time = time.perf_counter()

        response = rekognition.create_face_liveness_session()

        elapsed_time = time.perf_counter() - start_time

        print(
            f"LIVENESS CREATE AWS TIME: "
            f"{elapsed_time:.2f} seconds"
        )

        return Response({
            "session_id": response["SessionId"]
        })

    except ClientError as e:
        print(
            f"LIVENESS: AWS ClientError: {str(e)}"
        )

        return Response(
            {
                "error": e.response["Error"]["Message"]
            },
            status=400
        )

    except Exception as e:
        print(
            f"LIVENESS: Unexpected error: {str(e)}"
        )

        return Response(
            {
                "error": str(e)
            },
            status=500
        )


# =========================================================
# GET LIVENESS RESULT + FACE VERIFICATION
# =========================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def get_liveness_result(request):
    """
    Get AWS Rekognition Face Liveness result
    and compare the AWS liveness reference image
    with the employee's registered face.
    """

    total_start_time = time.perf_counter()

    # -----------------------------------------------------
    # Get request data
    # -----------------------------------------------------

    session_id = request.data.get('session_id')
    mobile_number = request.data.get('mobile_number')

    # -----------------------------------------------------
    # Validate session ID
    # -----------------------------------------------------

    if not session_id:
        return Response(
            {
                "error": "session_id is required"
            },
            status=400
        )

    # -----------------------------------------------------
    # Validate mobile number
    # -----------------------------------------------------

    if not mobile_number:
        return Response(
            {
                "error": "mobile_number is required"
            },
            status=400
        )

    # -----------------------------------------------------
    # Normalize mobile number
    # -----------------------------------------------------

    normalized = ''.join(
        filter(str.isdigit, str(mobile_number))
    )[-10:]

    try:

        # =================================================
        # 1. GET AWS LIVENESS RESULT
        # =================================================

        liveness_start_time = time.perf_counter()

        response = rekognition.get_face_liveness_session_results(
            SessionId=session_id
        )

        liveness_elapsed_time = (
            time.perf_counter() - liveness_start_time
        )

        print(
            f"LIVENESS RESULT AWS TIME: "
            f"{liveness_elapsed_time:.2f} seconds"
        )

        confidence = response.get(
            "Confidence",
            0
        )

        session_status = response.get(
            "Status"
        )

        reference_image = response.get(
            "ReferenceImage"
        )

        print(
            f"LIVENESS: Session={session_id}, "
            f"Status={session_status}, "
            f"Confidence={confidence}"
        )

        # =================================================
        # 2. CHECK LIVENESS STATUS
        # =================================================

        if session_status != "SUCCEEDED":

            total_elapsed_time = (
                time.perf_counter() - total_start_time
            )

            print(
                f"LIVENESS TOTAL TIME: "
                f"{total_elapsed_time:.2f} seconds"
            )

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
        # 3. GET REGISTERED EMPLOYEE FACE
        # =================================================

        db_start_time = time.perf_counter()

        face_record = EmployeeFaceData.objects.get(
            user__mobile_number=normalized
        )

        db_elapsed_time = (
            time.perf_counter() - db_start_time
        )

        print(
            f"FACE DB LOOKUP TIME: "
            f"{db_elapsed_time:.4f} seconds"
        )

        # =================================================
        # 4. DECODE REGISTERED FACE
        # =================================================

        decode_start_time = time.perf_counter()

        stored_image_bytes = base64.b64decode(
            face_record.face_image_base64
        )

        decode_elapsed_time = (
            time.perf_counter() - decode_start_time
        )

        print(
            f"FACE IMAGE DECODE TIME: "
            f"{decode_elapsed_time:.4f} seconds"
        )

        # =================================================
        # 5. GET AWS LIVENESS REFERENCE IMAGE
        # =================================================

        if not reference_image:

            total_elapsed_time = (
                time.perf_counter() - total_start_time
            )

            print(
                f"LIVENESS TOTAL TIME: "
                f"{total_elapsed_time:.2f} seconds"
            )

            return Response(
                {
                    "verified": False,
                    "message": "Liveness reference image not available."
                },
                status=400
            )

        if "Bytes" not in reference_image:

            total_elapsed_time = (
                time.perf_counter() - total_start_time
            )

            print(
                f"LIVENESS TOTAL TIME: "
                f"{total_elapsed_time:.2f} seconds"
            )

            return Response(
                {
                    "verified": False,
                    "message":
                    "Liveness reference image bytes not available."
                },
                status=400
            )

        liveness_image_bytes = reference_image["Bytes"]

        # =================================================
        # 6. COMPARE REGISTERED FACE WITH
        #    AWS LIVENESS REFERENCE IMAGE
        # =================================================

        print(
            f"FACE VERIFY: Starting comparison for "
            f"{normalized}..."
        )

        compare_start_time = time.perf_counter()

        comparison = rekognition.compare_faces(
            SourceImage={
                "Bytes": stored_image_bytes
            },
            TargetImage={
                "Bytes": liveness_image_bytes
            },
            SimilarityThreshold=80
        )

        compare_elapsed_time = (
            time.perf_counter() - compare_start_time
        )

        print(
            f"FACE COMPARE AWS TIME: "
            f"{compare_elapsed_time:.2f} seconds"
        )

        print(
            "FACE VERIFY: AWS comparison response received"
        )

        # =================================================
        # 7. CHECK FACE MATCH
        # =================================================

        matches = comparison.get(
            "FaceMatches",
            []
        )

        if matches:

            similarity = matches[0]["Similarity"]

            print(
                f"FACE VERIFY: Match found! "
                f"Similarity: {similarity}%"
            )

            total_elapsed_time = (
                time.perf_counter() - total_start_time
            )

            print(
                f"LIVENESS + FACE VERIFY TOTAL TIME: "
                f"{total_elapsed_time:.2f} seconds"
            )

            return Response(
                {
                    "verified": True,
                    "status": session_status,
                    "liveness_confidence": confidence,
                    "similarity": similarity,
                    "message":
                    "Liveness and face verification successful."
                }
            )

        # =================================================
        # 8. FACE DID NOT MATCH
        # =================================================

        print(
            "FACE VERIFY: No match found"
        )

        total_elapsed_time = (
            time.perf_counter() - total_start_time
        )

        print(
            f"LIVENESS + FACE VERIFY TOTAL TIME: "
            f"{total_elapsed_time:.2f} seconds"
        )

        return Response(
            {
                "verified": False,
                "status": session_status,
                "liveness_confidence": confidence,
                "similarity": 0,
                "message":
                "Face does not match the registered employee."
            },
            status=400
        )

    # =====================================================
    # EMPLOYEE FACE NOT FOUND
    # =====================================================

    except EmployeeFaceData.DoesNotExist:

        print(
            f"FACE VERIFY: No registered face found "
            f"for {normalized}"
        )

        total_elapsed_time = (
            time.perf_counter() - total_start_time
        )

        print(
            f"LIVENESS TOTAL TIME: "
            f"{total_elapsed_time:.2f} seconds"
        )

        return Response(
            {
                "verified": False,
                "message":
                "No registered face found for this employee."
            },
            status=404
        )

    # =====================================================
    # AWS ERROR
    # =====================================================

    except ClientError as e:

        print(
            f"LIVENESS/COMPARE: AWS ClientError: "
            f"{str(e)}"
        )

        total_elapsed_time = (
            time.perf_counter() - total_start_time
        )

        print(
            f"LIVENESS TOTAL TIME: "
            f"{total_elapsed_time:.2f} seconds"
        )

        return Response(
            {
                "error": e.response["Error"]["Message"]
            },
            status=400
        )

    # =====================================================
    # GENERAL ERROR
    # =====================================================

    except Exception as e:

        print(
            f"LIVENESS/COMPARE: Unexpected error: "
            f"{str(e)}"
        )

        total_elapsed_time = (
            time.perf_counter() - total_start_time
        )

        print(
            f"LIVENESS TOTAL TIME: "
            f"{total_elapsed_time:.2f} seconds"
        )

        return Response(
            {
                "error": str(e)
            },
            status=500
        )


# =========================================================
# CHECK FACE REGISTRATION STATUS
# =========================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def check_face_status(request):
    """Check if a mobile number has a face registered"""

    mobile_number = request.data.get(
        'mobile_number'
    )

    if not mobile_number:
        return Response(
            {
                "error": "Mobile number required"
            },
            status=400
        )

    normalized = ''.join(
        filter(str.isdigit, str(mobile_number))
    )[-10:]

    # -----------------------------------------------------
    # Check if user exists
    # -----------------------------------------------------

    if not CustomUser.objects.filter(
        mobile_number=normalized
    ).exists():

        return Response(
            {
                "error": "User not found in records",
                "exists": False
            },
            status=404
        )

    # -----------------------------------------------------
    # Check if face data exists
    # -----------------------------------------------------

    face_exists = EmployeeFaceData.objects.filter(
        user__mobile_number=normalized
    ).exists()

    return Response(
        {
            "mobile_number": normalized,
            "is_face_registered": face_exists,
            "exists": True
        }
    )


# =========================================================
# REGISTER FACE
# =========================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def register_face(request):
    """Register face data for an employee,
    ensuring no duplicates exist.
    """

    mobile_number = request.data.get(
        'mobile_number'
    )

    new_face_base64 = request.data.get(
        'face_image_base64'
    )

    if not mobile_number or not new_face_base64:

        return Response(
            {
                "error":
                "Mobile number and image data required"
            },
            status=400
        )

    normalized_new = ''.join(
        filter(str.isdigit, str(mobile_number))
    )[-10:]

    new_face_bytes = base64.b64decode(
        new_face_base64
    )

    # =====================================================
    # SECURITY CHECK: PREVENT DUPLICATE FACES
    # =====================================================

    existing_faces = EmployeeFaceData.objects.exclude(
        user__mobile_number=normalized_new
    )

    for face_record in existing_faces:

        try:

            stored_face_bytes = base64.b64decode(
                face_record.face_image_base64
            )

            comparison = rekognition.compare_faces(
                SourceImage={
                    'Bytes': stored_face_bytes
                },
                TargetImage={
                    'Bytes': new_face_bytes
                },
                SimilarityThreshold=90
            )

            if comparison.get('FaceMatches'):

                return Response(
                    {
                        "error":
                        "This face is already registered "
                        "to another employee account.",
                        "code":
                        "DUPLICATE_FACE"
                    },
                    status=400
                )

        except Exception as e:

            print(
                f"Skipping comparison for "
                f"{face_record.user.mobile_number}: "
                f"{str(e)}"
            )

            continue

    # =====================================================
    # END SECURITY CHECK
    # =====================================================

    serializer = FaceRegistrationSerializer(
        data=request.data
    )

    if serializer.is_valid():

        serializer.save()

        # =================================================
        # SYNC PHOTO TO EMPLOYEE PROFILE
        # =================================================

        try:

            from django.core.files.base import ContentFile

            from employees.models import Customuser as EmployeeRecord

            employee = EmployeeRecord.objects.get(
                user__mobile_number=normalized_new
            )

            image_name = (
                f"face_{normalized_new}.jpg"
            )

            employee.photo.save(
                image_name,
                ContentFile(new_face_bytes),
                save=True
            )

            print(
                f"Successfully synced face photo "
                f"for {normalized_new}"
            )

        except Exception as e:

            print(
                f"Failed to sync photo to employee "
                f"profile: {str(e)}"
            )

        # =================================================
        # END SYNC
        # =================================================

        return Response(
            {
                "message":
                "Face data registered successfully"
            },
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


# =========================================================
# OLD / DIRECT FACE VERIFICATION
# =========================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_face(request):
    """Verify live face against stored reference image"""

    mobile_number = request.data.get(
        'mobile_number'
    )

    captured_image_base64 = request.data.get(
        'face_image_base64'
    )

    if not mobile_number or not captured_image_base64:

        return Response(
            {
                "error":
                "Mobile number and image data required"
            },
            status=400
        )

    normalized = ''.join(
        filter(str.isdigit, str(mobile_number))
    )[-10:]

    try:

        # =================================================
        # GET STORED REFERENCE IMAGE
        # =================================================

        face_record = EmployeeFaceData.objects.get(
            user__mobile_number=normalized
        )

        stored_image_bytes = base64.b64decode(
            face_record.face_image_base64
        )

        # =================================================
        # DECODE CAPTURED IMAGE
        # =================================================

        captured_image_bytes = base64.b64decode(
            captured_image_base64
        )

        # =================================================
        # COMPARE FACES USING AWS REKOGNITION
        # =================================================

        print(
            f"DEBUG FACE: Starting comparison "
            f"for {normalized}..."
        )

        try:

            compare_start_time = time.perf_counter()

            response = rekognition.compare_faces(
                SourceImage={
                    'Bytes': stored_image_bytes
                },
                TargetImage={
                    'Bytes': captured_image_bytes
                },
                SimilarityThreshold=80
            )

            compare_elapsed_time = (
                time.perf_counter() - compare_start_time
            )

            print(
                f"DEBUG FACE: AWS COMPARE TIME: "
                f"{compare_elapsed_time:.2f} seconds"
            )

            print(
                "DEBUG FACE: AWS Response received"
            )

        except ClientError as e:

            print(
                f"DEBUG FACE: AWS ClientError: "
                f"{str(e)}"
            )

            return Response(
                {
                    "error":
                    f"Face verification failed: "
                    f"{e.response['Error']['Message']}"
                },
                status=400
            )

        matches = response.get(
            'FaceMatches',
            []
        )

        if matches:

            similarity = matches[0]['Similarity']

            print(
                f"DEBUG FACE: Match found! "
                f"Similarity: {similarity}%"
            )

            return Response(
                {
                    "verified": True,
                    "confidence": similarity,
                    "similarity": similarity,
                    "message":
                    "Face verified successfully"
                }
            )

        else:

            print(
                "DEBUG FACE: No match found"
            )

            return Response(
                {
                    "verified": False,
                    "confidence": 0,
                    "message":
                    "Face verification failed. "
                    "No match found. "
                    "Please look directly at the camera."
                },
                status=400
            )

    except EmployeeFaceData.DoesNotExist:

        print(
            f"DEBUG FACE: No record for {normalized}"
        )

        return Response(
            {
                "error":
                "No reference face image found. "
                "Please register first."
            },
            status=404
        )

    except Exception as e:

        print(
            f"DEBUG FACE: Unexpected error: "
            f"{str(e)}"
        )

        return Response(
            {
                "error":
                f"Internal Error: {str(e)}"
            },
            status=500
        )


# =========================================================
# GET FACE DETAILS
# =========================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def get_face_details(request, mobile_number):
    """Retrieve face data for a specific mobile number"""

    normalized = ''.join(
        filter(str.isdigit, str(mobile_number))
    )[-10:]

    try:

        face_data = EmployeeFaceData.objects.get(
            user__mobile_number=normalized
        )

        serializer = FaceDataSerializer(
            face_data
        )

        return Response(
            serializer.data
        )

    except EmployeeFaceData.DoesNotExist:

        return Response(
            {
                "error": "Face data not found"
            },
            status=status.HTTP_404_NOT_FOUND
        )