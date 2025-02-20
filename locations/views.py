from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from .models import Location
from .serializers import LocationSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication

@api_view(['POST', 'GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def location_list_create(request):
    if request.method == 'POST':
        # Automatically set the organization to the user's organization
        request.data['org'] = request.user.org_id
        serializer = LocationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':
        # Filter locations by the user's organization
        locations = Location.objects.filter(org=request.user.org_id)
        serializer = LocationSerializer(locations, many=True)
        return Response(serializer.data)

@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def location_detail(request, location_id):
    try:
        location = Location.objects.get(location_id=location_id, org=request.user.org_id)
    except Location.DoesNotExist:
        return Response({'error': 'Location not found or not accessible'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = LocationSerializer(location)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = LocationSerializer(location, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        location.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)