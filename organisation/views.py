from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser
from .serializers import CustomUserSerializer, ProfileSerializer, Loginserializer
from rest_framework_simplejwt.authentication import JWTAuthentication

def mobile_number_variants(mobile_number):
    normalized = ''.join(filter(str.isdigit, str(mobile_number)))
    variants = [normalized]
    if normalized.startswith('91') and len(normalized) > 10:
        variants.append(normalized[2:])
    elif len(normalized) == 10:
        variants.append(f'91{normalized}')
    return list(dict.fromkeys(variants))

@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    # Handle missing email by providing a default
    data = request.data.copy()
    if not data.get('email'):
        # Generate a placeholder email based on mobile number
        data['email'] = f"{data.get('mobile_number', 'user')}@placeholder.com"
    
    serializer = CustomUserSerializer(data=data)
    if serializer.is_valid():
            user = CustomUser.objects.create(
                mobile_number=serializer.validated_data['mobile_number'],
                name=serializer.validated_data['name'],
                email=serializer.validated_data['email']
            )
            generated_password = user.generate_password()
            # user.password = generated_password # Standard Django hashing is now handled in manager
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
            mobile_number = serializer.validated_data['mobile_number']
            password = serializer.validated_data['password']
            
            # 🔍 Find user using variants (handles 91 prefix)
            user = CustomUser.objects.filter(
                mobile_number__in=mobile_number_variants(mobile_number)
            ).first()

            if not user:
                print(f"🕵️ Login Failed: User with mobile {mobile_number} not found.")
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

            print(f"👤 Login Attempt: Found user {user.name} ({user.mobile_number})")
            
            # 🔐 Use Django's secure check_password method
            if user.check_password(password):
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
                
                # Custom claims for frontend role and organization handling
                access_token['role'] = 'organization' if user.is_organization else 'employee'
                access_token['org_id'] = user.org_id
                
                return Response({
                    'access': str(access_token),
                    'refresh': str(refresh),
                    'org_id': user.org_id,
                    'role': access_token['role']
                })
            
            return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
            
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Login Error: {e}")
            return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
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
