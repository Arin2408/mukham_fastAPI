from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from .models import Designation
from departments.models import Department
from .serializers import DesignationSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_designation(request):
    serializer = DesignationSerializer(data=request.data)
    if serializer.is_valid():
        # Ensure the designation is associated with the user's organization
        department_id = serializer.validated_data['department'].department_id
        try:
            department = Department.objects.get(department_id=department_id, org=request.user.org_id)
        except Department.DoesNotExist:
            return Response({"error": "Department not found or not accessible"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer.validated_data['department'] = department
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_designations(request):
    # Filter designations by the user's organization
    designations = Designation.objects.filter(department__org=request.user.org_id)
    serializer = DesignationSerializer(designations, many=True)
    return Response(serializer.data)

@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_designation(request, designation_id):
    try:
        designation = Designation.objects.get(designation_id=designation_id, department__org=request.user.org_id)
    except Designation.DoesNotExist:
        return Response({"error": "Designation not found or not accessible"}, status=status.HTTP_404_NOT_FOUND)

    serializer = DesignationSerializer(designation, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_designation(request, designation_id):
    try:
        designation = Designation.objects.get(designation_id=designation_id, department__org=request.user.org_id)
    except Designation.DoesNotExist:
        return Response({"error": "Designation not found or not accessible"}, status=status.HTTP_404_NOT_FOUND)

    designation.delete()
    return Response({"message": "Designation deleted successfully"}, status=status.HTTP_204_NO_CONTENT)