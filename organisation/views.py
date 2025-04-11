from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser
from employees.models import Customuser
from .serializers import CustomUserSerializer, ProfileSerializer, Loginserializer
from rest_framework_simplejwt.authentication import JWTAuthentication

@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    serializer = CustomUserSerializer(data=request.data)
    if serializer.is_valid():
            user = CustomUser.objects.create(
                mobile_number=serializer.validated_data['mobile_number'],
                name=serializer.validated_data['name']
            )
            generated_password = user.generate_password()
            user.password = generated_password
            user.save()

            return Response({
                'mobile_number': user.mobile_number,
                'generated_password': generated_password,
                'message': 'User created successfully'
            }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    serializer = Loginserializer(data=request.data)
    if serializer.is_valid():
        try:
            user = CustomUser.objects.get(
                mobile_number=serializer.validated_data['mobile_number']
            )
            # Directly compare the raw password
            if user.password == serializer.validated_data['password']:
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
                access_token['role'] = 'organization' if user.is_organization else 'employee'
                access_token['org_id'] = user.org_id 
                # Add role to token claims
                return Response({
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'org_id': user.org_id,
                    'role': 'organization' if user.is_organization else 'employee'
                })
            return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def profile_view(request, org_id):
    try:
        user = CustomUser.objects.get(org_id=org_id)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = ProfileSerializer(user)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = ProfileSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_organisation(request, org_id):
    try:
        # Fetch the organization based on org_id
        organisation = CustomUser.objects.get(org_id=org_id)
    except CustomUser.DoesNotExist:
        return Response({"error": "Organisation not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = CustomUserSerializer(organisation)
    return Response(serializer.data, status=status.HTTP_200_OK)