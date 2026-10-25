from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, Client
from django.core.cache import cache

class UserSerializer(serializers.ModelSerializer):
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
        # Required validation yahan handle karenge model ke bajaye:
        extra_kwargs = {
            'email': {
                'required': True, 
                'allow_null': False, 
                'allow_blank': False,
                'error_messages': {'required': 'Email is required.'}
            },
            'username': {
                'required': True, 
                'allow_null': False, 
                'allow_blank': False,
                'error_messages': {'required': 'Username is required.'}
            },
            'first_name': {
                'required': True, 
                'allow_null': False, 
                'allow_blank': False,
                'error_messages': {'required': 'First name is required.'}
            },
        }

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
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password],
        error_messages={'required': 'Password is required.'}
    )

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        return User.objects.create_user(password=password, **validated_data)  # hash hota hai


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


# ==========================================
# OTP RATE LIMIT HELPERS
# ==========================================
def check_otp_limit(email):
    cache_key = f"otp_request_count:{email}"
    attempts = cache.get(cache_key, 0)
    if attempts >= 3:
        raise serializers.ValidationError(
            "You have exceeded the maximum number of OTP requests. Please try again after 12 hours."
        )

def record_otp_attempt(email):
    cache_key = f"otp_request_count:{email}"
    TWELVE_HOURS = 12 * 60 * 60  # 43200 seconds (12 ghante)
    attempts = cache.get(cache_key, 0)
    if attempts == 0:
        cache.set(cache_key, 1, timeout=TWELVE_HOURS)
    else:
        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, attempts + 1, timeout=TWELVE_HOURS)


# ==========================================
# OTP & AUTH SERIALIZERS
# ==========================================
class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.lower().strip()
        check_otp_limit(email)  # <-- 3 baar se zyada hoga to yahi rok dega
        return email

    def record_attempt(self):
        email = self.validated_data['email'].lower().strip()
        record_otp_attempt(email)  # <-- attempt count +1 karega


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.lower().strip()
        check_otp_limit(email)  # <-- Forgot password me bhi 3 limit lagegi
        return email

    def record_attempt(self):
        email = self.validated_data['email'].lower().strip()
        record_otp_attempt(email)  # <-- attempt count +1 karega


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])



class ClientSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    deleted_by = serializers.SerializerMethodField()
    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
        # Client ke required fields:
        extra_kwargs = {
            'first_name': {
                'required': True, 
                'allow_null': False, 
                'allow_blank': False,
                'error_messages': {'required': 'First name is required.'}
            },
            'email_id': {
                'required': True, 
                'allow_null': False, 
                'allow_blank': False,
                'error_messages': {'required': 'Client email ID is required.'}
            },
        }

    def _format_user(self, user):
        if not user:
            return None
        name = f"{user.first_name} {user.last_name}".strip()
        return {
            "id": user.id,
            "name": name if name else user.username,
            "email": user.email,
        }

    def get_created_by(self, obj):
        return self._format_user(obj.created_by)

    def get_updated_by(self, obj):
        return self._format_user(obj.updated_by)

    def get_deleted_by(self, obj):
        return self._format_user(obj.deleted_by)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # 1. Jo fields null hain unhe response se hata do
        for field in ['deleted_at', 'deleted_by', 'updated_by']:
            if ret.get(field) is None:
                ret.pop(field, None)
        
        # 2. Agar abhi tak update nahi hua hai, to updated_at bhi mat dikhao
        if not instance.updated_by:
            ret.pop('updated_at', None)

        return ret


