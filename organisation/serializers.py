from rest_framework import serializers
from .models import CustomUser
from django.contrib.auth import authenticate

class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['name', 'email', 'details', 'mobile_number', 'is_organization']
        extra_kwargs = {
            'name': {'required': True},
            'mobile_number': {'required': True},
            'email': {'required': False},  # Email is now optional
            'details': {'required': False}
        }

    def validate_mobile_number(self, value):
        from .views import normalize_mobile
        normalized = normalize_mobile(value)
        if CustomUser.objects.filter(mobile_number=normalized).exists():
            raise serializers.ValidationError("A user with this mobile number already exists.")
        return normalized

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['name', 'email', 'details', 'mobile_number']
        read_only_fields = ['org_id', 'mobile_number']

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.email = validated_data.get('email', instance.email)
        instance.details = validated_data.get('details', instance.details)
        instance.save()
        return instance
    
class Loginserializer(serializers.Serializer):

    mobile_number = serializers.CharField()
    password = serializers.CharField()
    class Meta:
        model = CustomUser
        fields = ['mobile_number', 'password']