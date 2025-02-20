from rest_framework import serializers
from .models import CustomUser

class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['name', 'email', 'details', 'mobile_number']
        extra_kwargs = {
            'name': {'required': True},
            'mobile_number': {'required': True},
            'email': {'required': False},
            'details': {'required': False}
        }

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