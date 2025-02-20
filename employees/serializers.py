from rest_framework import serializers
from .models import Customuser

class Signupserializer(serializers.ModelSerializer):
    class Meta:
        model = Customuser
        fields = '__all__'

    def create(self, validated_data):
        return Customuser.objects.create(**validated_data)

class Loginserializer(serializers.ModelSerializer):
    user_name = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Customuser
        fields = ['user_name', 'password']