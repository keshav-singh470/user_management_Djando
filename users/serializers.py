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

    def to_internal_value(self, data):
        # 1. Request data ki copy banate hain (taki mutate kar sakein)
        data = data.copy()

        # 2. String fields se aage-peeche ke faltu spaces hatana (.strip())
        for key in data:
            if isinstance(data[key], str):
                data[key] = data[key].strip()

        # 3. Email & Username ko hamesha Lowercase karna
        if 'email' in data and isinstance(data['email'], str):
            data['email'] = data['email'].lower()
        if 'username' in data and isinstance(data['username'], str):
            data['username'] = data['username'].lower()

        # 4. Gender ko case-insensitive handle karna ('male', 'MALE' -> 'Male')
        if 'gender' in data and isinstance(data['gender'], str):
            g = data['gender'].lower()
            gender_map = {'male': 'Male', 'female': 'Female', 'other': 'Other'}
            if g in gender_map:
                data['gender'] = gender_map[g]

        # 5. Status ko case-insensitive handle karna ('active', 'ACTIVE' -> 'Active')
        if 'status' in data and isinstance(data['status'], str):
            s = data['status'].lower()
            status_map = {'active': 'Active', 'inactive': 'Inactive'}
            if s in status_map:
                data['status'] = status_map[s]

        # 6. Blood Group ('o+', 'ab+' -> 'O+', 'AB+')
        if 'blood_group' in data and isinstance(data['blood_group'], str):
            data['blood_group'] = data['blood_group'].upper()

        # 7. Profiles ('standard', 'admin', 'developer', etc.)
        if 'profiles' in data and isinstance(data['profiles'], str):
            p = data['profiles'].lower()
            profiles_map = {
                'administrator': 'Administrator',
                'standard': 'Standard',
                'developer': 'Developer',
                'client': 'Client',
                'human resource': 'Human Resource',
            }
            if p in profiles_map:
                data['profiles'] = profiles_map[p]

        # 8. First Name aur Last Name ka pehla letter Capital karna (Title Case)
        if 'first_name' in data and isinstance(data['first_name'], str):
            data['first_name'] = data['first_name'].capitalize()
        if 'last_name' in data and isinstance(data['last_name'], str):
            data['last_name'] = data['last_name'].capitalize()

        return super().to_internal_value(data)


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