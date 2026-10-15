from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Read + Update (password nahi aata)"""
    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 'username', 'profiles',
            'date_of_birth', 'gender', 'nationality', 'image', 'blood_group',
            'phone', 'permanent_address', 'current_address',
            'emergency_contact_name', 'emergency_contact_number',
            'emergency_contact_relationship', 'status',
        ]
        read_only_fields = ['id']


class UserCreateSerializer(UserSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        return User.objects.create_user(password=password, **validated_data)  # hash hota hai


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])