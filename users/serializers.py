from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, Client, Profile, Project, ProjectAttachment
from django.core.cache import cache
from django.db.models import Q

import os
from django.contrib.auth.password_validation import validate_password
 

class DynamicProfileField(serializers.SlugRelatedField):
    """If the profile does not exist in the database, it will create the profile automatically."""
    def to_internal_value(self, data):
        if not data:
            return None
        profile_name = str(data).strip()
        profile, _ = Profile.objects.get_or_create(
            name=profile_name,
            defaults={'description': f'{profile_name} profile'}
        )
        return profile

class UserSerializer(serializers.ModelSerializer):
    profiles = DynamicProfileField(
        slug_field='name',
        queryset=Profile.objects.all(),
        required=False,
        allow_null=True
    )
 
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
        # We will handle the required validation here instead of in the model.
        extra_kwargs = {
            'email': {
                'required': True, 
                'allow_null': False, 
                'allow_blank': False,
                'error_messages': {'required': 'Email is required.'}
            },
            'username': {
                'required': False, 
                'allow_blank': True,
                 
            },
            'first_name': {
                'required': False, 
                'allow_blank': True,
                 
            },
        }

    def to_internal_value(self, data):
        # 1. We create a copy of the request data so that we can modify it without affecting the original data
        data = data.copy()

        # 2. Remove unnecessary spaces from the beginning and end of string fields using .strip()
        for key in data:
            if isinstance(data[key], str):
                data[key] = data[key].strip()

        # 3. Always convert the email and username to lowercase
        if 'email' in data and isinstance(data['email'], str):
            data['email'] = data['email'].lower()
        if 'username' in data and isinstance(data['username'], str):
            data['username'] = data['username'].lower()

        # 4. Handle gender case-insensitively ('male', 'MALE' → 'Male').
        if 'gender' in data and isinstance(data['gender'], str):
            g = data['gender'].lower()
            gender_map = {'male': 'Male', 'female': 'Female', 'other': 'Other'}
            if g in gender_map:
                data['gender'] = gender_map[g]

        # 5. Handle the status case-insensitively ('active', 'ACTIVE' → 'Active')
        if 'status' in data and isinstance(data['status'], str):
            s = data['status'].lower()
            status_map = {'active': 'Active', 'inactive': 'Inactive'}
            if s in status_map:
                data['status'] = status_map[s]

        # 6. Blood Group ('o+', 'ab+' -> 'O+', 'AB+')
        if 'blood_group' in data and isinstance(data['blood_group'], str):
            data['blood_group'] = data['blood_group'].upper()


        # 8. Capitalize the first letter of the first name and last name.
        if 'first_name' in data and isinstance(data['first_name'], str):
            data['first_name'] = data['first_name'].capitalize()
        if 'last_name' in data and isinstance(data['last_name'], str):
            data['last_name'] = data['last_name'].capitalize()

        return super().to_internal_value(data)


class UserCreateSerializer(UserSerializer):
    password = serializers.CharField(
        write_only=True, 
        required=False,        # No need to send request password 
        allow_blank=True,    
    )

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['password']

    def create(self, validated_data):
        email = validated_data.get('email', '')
        prefix = email.split('@')[0] if '@' in email else email
        dynamic_default_password = f"{prefix}@123"

        password = validated_data.pop('password', None) or dynamic_default_password
    
        if not validated_data.get('username'):
            validated_data['username'] = email

        # Default profile assign karna (Requirement 1 ke liye):
        if not validated_data.get('profiles'):
            default_profile, _ = Profile.objects.get_or_create(
                name='Standard', 
                defaults={'description': 'Default user profile'}
            )
            validated_data['profiles'] = default_profile

        return User.objects.create_user(password=password, **validated_data)



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
    TWELVE_HOURS = 12 * 60 * 60  # 43200 seconds (12 hours)
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
        check_otp_limit(email)  # <-- If it happens more than three times, it will be stopped here.
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
        check_otp_limit(email)  # <-- The same three-attempt limit will also be applied to the forgot password process.
        return email

    def record_attempt(self):
        email = self.validated_data['email'].lower().strip()
        record_otp_attempt(email)  # <-- attempt would be count +1


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

# ==========================================
# PROFILE SERIALIZER
# ==========================================
class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'name': {
                'required': True,
                'allow_blank': False,
                'error_messages': {'required': 'Profile name is required.'}
            }
        }

class ClientSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    deleted_by = serializers.SerializerMethodField()
    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
        # Client-required fields
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
        # 1. Remove the fields that have null values from the response.
        for field in ['deleted_at', 'deleted_by', 'updated_by']:
            if ret.get(field) is None:
                ret.pop(field, None)
        
        # If the record has not been updated yet, do not display updated_at
        if not instance.updated_by:
            ret.pop('updated_at', None)

        return ret


# Project Serializer

class ManagerRelatedField(serializers.PrimaryKeyRelatedField):
    """
This field can accept an ID (24), email (`admin@gmail.com`), 
username (`admin`), or name (`Keshav`).
    """
    def to_internal_value(self, data):
        # 1. If the ID is a number, such as integer `24` or string `"24"`.
        if isinstance(data, int) or (isinstance(data, str) and data.isdigit()):
            try:
                return self.get_queryset().get(pk=int(data))
            except User.DoesNotExist:
                raise serializers.ValidationError(f"User with ID {data} does not exist.")

        # 2.If it is a string, such as an email, username, or name.
        if isinstance(data, str):
            user = self.get_queryset().filter(
                Q(email__iexact=data) | 
                Q(username__iexact=data) | 
                Q(first_name__iexact=data)
            ).first()

            if user:
                return user
            raise serializers.ValidationError(f"No manager found with email, username, or name '{data}'.")

        self.fail('incorrect_type', data_type=type(data).__name__)


class ProjectSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    deleted_by = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    attachments_count = serializers.SerializerMethodField()

    # Here, assign a custom field to the `assigned_manager` field.
    assigned_manager = ManagerRelatedField(
        queryset=User.objects.all(), 
        required=False, 
        allow_null=True
    )

    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by', 'deleted_by']
        extra_kwargs = {
            'title': {'required': True, 'error_messages': {'required': 'Project title is required.'}},
            'type': {'required': True, 'error_messages': {'required': 'Project type is required.'}},
            'client': {'required': False, 'allow_null': True},
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

     # Helper method for formatting client data in response
    def _format_client(self, client):
        if not client:
            return None
        name = f"{client.first_name or ''} {client.last_name or ''}".strip()
        return {
            "id": client.id,
            "name": name if name else "Unnamed Client",
            "email": client.email_id,
            "contact_no": client.contact_no,
        }

    def get_created_by(self, obj):
        return self._format_user(obj.created_by)

    def get_updated_by(self, obj):
        return self._format_user(obj.updated_by)

    def get_deleted_by(self, obj):
        return self._format_user(obj.deleted_by)

    def get_attachments(self, obj):                   # Project_Attachment 
        request = self.context.get('request')
        return ProjectAttachmentSerializer(
            obj.attachments.all(), many=True, context={'request': request}
        ).data

    def get_attachments_count(self, obj):        #Attachmnet
        return obj.attachments.count()

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Format client in response like created_by
        ret['client'] = self._format_client(instance.client)
        ret['assigned_manager'] = self._format_user(instance.assigned_manager)
        # Do not include null audit fields in the response.
        for field in ['deleted_at', 'deleted_by', 'updated_by']:
            if ret.get(field) is None:
                ret.pop(field, None)
        if not instance.updated_by:
            ret.pop('updated_at', None)
        # List me files ki poori list mat bhejo, sirf detail me bhejo
        if not self.context.get('include_attachments'):
            ret.pop('attachments', None)
        return ret

# ==========================================
# PROJECT ATTACHMENT SERIALIZER
# ==========================================
class ProjectAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.SerializerMethodField()

    class Meta:
        model = ProjectAttachment
        fields = ['id', 'file', 'file_name', 'uploaded_by', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at', 'uploaded_by']
        extra_kwargs = {
            'file': {
                'required': True,
                'error_messages': {'required': 'Please upload a file.'}
            }
        }

    def get_uploaded_by(self, obj):
        if not obj.uploaded_by:
            return None
        name = f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip()
        return {
            "id": obj.uploaded_by.id,
            "name": name if name else obj.uploaded_by.username,
            "email": obj.uploaded_by.email,
        }

    def validate_file(self, value):
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("File size must not exceed 10MB.")

        allowed = ['.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx', '.xlsx', '.txt']
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in allowed:
            raise serializers.ValidationError(f"File type '{ext}' is not allowed.")
        return value