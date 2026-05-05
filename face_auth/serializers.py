from rest_framework import serializers
from .models import EmployeeFaceData
from organisation.models import CustomUser

class FaceRegistrationSerializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField(write_only=True)

    class Meta:
        model = EmployeeFaceData
        fields = ['mobile_number', 'face_image_base64']

    def validate_mobile_number(self, value):
        # Normalize mobile number
        normalized = ''.join(filter(str.isdigit, str(value)))[-10:]
        if not CustomUser.objects.filter(mobile_number=normalized).exists():
            raise serializers.ValidationError("Mobile number not found in employee records.")
        return normalized

    def create(self, validated_data):
        mobile_number = validated_data.pop('mobile_number')
        user = CustomUser.objects.get(mobile_number=mobile_number)
        
        # Update or create face data
        face_data, created = EmployeeFaceData.objects.update_or_create(
            user=user,
            defaults={'face_image_base64': validated_data['face_image_base64']}
        )
        return face_data

class FaceDataSerializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)
    
    class Meta:
        model = EmployeeFaceData
        fields = ['mobile_number', 'face_image_base64', 'updated_at']
