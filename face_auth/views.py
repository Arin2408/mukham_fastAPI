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
from botocore.exceptions import ClientError

# Initialize AWS Client
rekognition = boto3.client(
    'rekognition',
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_DEFAULT_REGION
)

@api_view(['POST'])
@permission_classes([AllowAny])
def check_face_status(request):
    """Check if a mobile number has a face registered"""
    mobile_number = request.data.get('mobile_number')
    if not mobile_number:
        return Response({"error": "Mobile number required"}, status=400)
    
    normalized = ''.join(filter(str.isdigit, str(mobile_number)))[-10:]
    
    # First check if user exists in main DB
    if not CustomUser.objects.filter(mobile_number=normalized).exists():
        return Response({"error": "User not found in records", "exists": False}, status=404)
    
    # Check if face data exists
    face_exists = EmployeeFaceData.objects.filter(user__mobile_number=normalized).exists()
    
    return Response({
        "mobile_number": normalized,
        "is_face_registered": face_exists,
        "exists": True
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def register_face(request):
    """Register face data for an employee, ensuring no duplicates exist"""
    mobile_number = request.data.get('mobile_number')
    new_face_base64 = request.data.get('face_image_base64')

    if not mobile_number or not new_face_base64:
        return Response({"error": "Mobile number and image data required"}, status=400)

    normalized_new = ''.join(filter(str.isdigit, str(mobile_number)))[-10:]
    new_face_bytes = base64.b64decode(new_face_base64)

    # --- SECURITY CHECK: Prevent Duplicate Faces ---
    # Check if this face already belongs to someone else
    existing_faces = EmployeeFaceData.objects.exclude(user__mobile_number=normalized_new)
    
    for face_record in existing_faces:
        try:
            stored_face_bytes = base64.b64decode(face_record.face_image_base64)
            
            comparison = rekognition.compare_faces(
                SourceImage={'Bytes': stored_face_bytes},
                TargetImage={'Bytes': new_face_bytes},
                SimilarityThreshold=90  # High threshold for identity matching
            )
            
            if comparison.get('FaceMatches'):
                return Response({
                    "error": "This face is already registered to another employee account.",
                    "code": "DUPLICATE_FACE"
                }, status=400)
                
        except Exception as e:
            print(f"Skipping comparison for {face_record.user.mobile_number}: {str(e)}")
            continue
    # --- END SECURITY CHECK ---

    serializer = FaceRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        
        # --- NEW: Sync photo to Employee Profile for ID Card ---
        try:
            from django.core.files.base import ContentFile
            from employees.models import Customuser as EmployeeRecord
            
            employee = EmployeeRecord.objects.get(user__mobile_number=normalized_new)
            image_name = f"face_{normalized_new}.jpg"
            employee.photo.save(image_name, ContentFile(new_face_bytes), save=True)
            print(f"Successfully synced face photo for {normalized_new}")
        except Exception as e:
            print(f"Failed to sync photo to employee profile: {str(e)}")
        # --- END SYNC ---

        return Response({"message": "Face data registered successfully"}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_face(request):
    """Verify live face against stored reference image"""
    mobile_number = request.data.get('mobile_number')
    captured_image_base64 = request.data.get('face_image_base64')

    if not mobile_number or not captured_image_base64:
        return Response({"error": "Mobile number and image data required"}, status=400)

    normalized = ''.join(filter(str.isdigit, str(mobile_number)))[-10:]
    
    try:
        # Get stored reference image
        face_record = EmployeeFaceData.objects.get(user__mobile_number=normalized)
        stored_image_bytes = base64.b64decode(face_record.face_image_base64)
        
        # Decode captured image
        captured_image_bytes = base64.b64decode(captured_image_base64)
        
        # Compare faces using AWS Rekognition
        print(f"DEBUG FACE: Starting comparison for {normalized}...")
        try:
            response = rekognition.compare_faces(
                SourceImage={'Bytes': stored_image_bytes},
                TargetImage={'Bytes': captured_image_bytes},
                SimilarityThreshold=80
            )
            print(f"DEBUG FACE: AWS Response received")
        except ClientError as e:
            print(f"DEBUG FACE: AWS ClientError: {str(e)}")
            return Response({"error": f"Face verification failed: {e.response['Error']['Message']}"}, status=400)

        matches = response.get('FaceMatches', [])
        
        if matches:
            similarity = matches[0]['Similarity']
            print(f"DEBUG FACE: Match found! Similarity: {similarity}%")
            return Response({
                "verified": True,
                "confidence": similarity,  # Use confidence/similarity interchangeably here
                "similarity": similarity,
                "message": "Face verified successfully"
            })
        else:
            print(f"DEBUG FACE: No match found")
            return Response({
                "verified": False,
                "confidence": 0,
                "message": "Face verification failed. No match found. Please look directly at the camera."
            }, status=400)

    except EmployeeFaceData.DoesNotExist:
        print(f"DEBUG FACE: No record for {normalized}")
        return Response({"error": "No reference face image found. Please register first."}, status=404)
    except Exception as e:
        print(f"DEBUG FACE: Unexpected error: {str(e)}")
        return Response({"error": f"Internal Error: {str(e)}"}, status=500)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_face_details(request, mobile_number):
    """Retrieve face data for a specific mobile number"""
    normalized = ''.join(filter(str.isdigit, str(mobile_number)))[-10:]
    try:
        face_data = EmployeeFaceData.objects.get(user__mobile_number=normalized)
        serializer = FaceDataSerializer(face_data)
        return Response(serializer.data)
    except EmployeeFaceData.DoesNotExist:
        return Response({"error": "Face data not found"}, status=status.HTTP_404_NOT_FOUND)
