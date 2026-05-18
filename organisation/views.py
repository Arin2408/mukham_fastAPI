from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser
from .serializers import CustomUserSerializer, ProfileSerializer, Loginserializer
from rest_framework_simplejwt.authentication import JWTAuthentication

def normalize_mobile(mobile_number):
    return ''.join(filter(str.isdigit, str(mobile_number)))[-10:]

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
            
            # 🔍 Find user using normalized 10-digit mobile number
            raw_mobile = mobile_number
            normalized_mobile = normalize_mobile(raw_mobile)
            print(f"DEBUG LOGIN: Searching for user with normalized mobile: {normalized_mobile}")
            user = CustomUser.objects.filter(
                mobile_number=normalized_mobile
            ).first()

            if not user:
                print(f"DEBUG LOGIN Failed: User NOT found for mobile '{normalized_mobile}'. Users in DB: {[u.mobile_number for u in CustomUser.objects.all()]}")
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

            print(f"DEBUG LOGIN: Found user '{user.name}' (ID: {user.org_id})")
            
            # 🔐 Use Django's secure check_password method
            pass_match = user.check_password(password)
            print(f"DEBUG LOGIN: Password Match result for '{password}': {pass_match}")

            if pass_match:
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
            import traceback
            print("LOGIN CRASHED!")
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
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

@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password(request):
    email = request.data.get('email')
    print(f"DEBUG: Received forgot password request for email: {email}")
    
    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = CustomUser.objects.get(email=email)
        # In a real app, you'd generate a token and a real link.
        # For now, we'll follow the prompt requirements.
        from django.core.mail import send_mail
        subject = 'Password Reset Request'
        message = f'Hi {user.name},\n\nYou requested a password reset. Click the link below to reset your password:\n\nhttp://localhost:3000/reset-password?email={email}\n\nIf you did not request this, please ignore this email.'
        
        send_mail(
            subject,
            message,
            None, # Uses DEFAULT_FROM_EMAIL
            [email],
            fail_silently=False,
        )
        
        return Response({"message": "Reset link sent"}, status=status.HTTP_200_OK)
    except CustomUser.DoesNotExist:
        # For security, we usually don't reveal if the email exists.
        # But for debugging, we'll return a clear error for now.
        return Response({"error": "User with this email does not exist"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"ERROR sending email: {str(e)}")
        return Response({"error": f"Failed to send email: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    email = request.data.get('email')
    new_password = request.data.get('password')
    
    if not email or not new_password:
        return Response({"error": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = CustomUser.objects.get(email=email)
        user.set_password(new_password)
        user.save()
        return Response({"message": "Password reset successfully"}, status=status.HTTP_200_OK)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
