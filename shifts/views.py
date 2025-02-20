from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from .models import Shift
from .serializers import ShiftSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from departments.models import Department
from organisation.models import CustomUser

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_shift(request):
    serializer = ShiftSerializer(data=request.data)
    if serializer.is_valid():
        # Ensure the shift is associated with the user's organization
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
def list_shifts(request):
    # Filter shifts by the user's organization
    shifts = Shift.objects.filter(department__org=request.user.org_id)
    serializer = ShiftSerializer(shifts, many=True)
    return Response(serializer.data)

@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_shift(request, shift_id):
    try:
        shift = Shift.objects.get(shift_id=shift_id, department__org=request.user.org_id)
    except Shift.DoesNotExist:
        return Response({"error": "Shift not found or not accessible"}, status=status.HTTP_404_NOT_FOUND)

    serializer = ShiftSerializer(shift, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_shift(request, shift_id):
    try:
        shift = Shift.objects.get(shift_id=shift_id, department__org=request.user.org_id)
    except Shift.DoesNotExist:
        return Response({"error": "Shift not found or not accessible"}, status=status.HTTP_404_NOT_FOUND)

    shift.delete()
    return Response({"message": "Shift deleted successfully"}, status=status.HTTP_204_NO_CONTENT)