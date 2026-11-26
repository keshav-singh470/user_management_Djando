from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import time
from django.core.cache import cache
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q, ProtectedError, Prefetch, Count

from .models import User, Client, Project, Profile, ProjectTask, TaskComment, LookupValue, ActivityLog, TaskAttachment
from .serializers import *
from .utils import create_and_send_otp, send_welcome_email, verify_otp, send_project_created_emails
from .permissions import (UserWritePermission, ProfileWritePermission,
                          ClientWritePermission, ProjectWritePermission, role_of, IsNotClient)
from .access import visible_projects, visible_tasks, can_see_inactive

from rest_framework.exceptions import (NotFound, PermissionDenied, AuthenticationFailed, Throttled,ValidationError as DRFValidationError)
from .exceptions import APIError
from drf_spectacular.utils import extend_schema

def fetch_active(model, pk, label, restore_hint=None):
    if pk < 1:
        raise APIError(
            f'{label} id {pk} is not valid. IDs start from 1.',
            status_code=404,
            hint='Use the list endpoint to see valid ids.')
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        raise APIError(
            f'{label} with id {pk} is not available. It was never created, or it was permanently deleted.',
            status_code=404,
            hint='Check the id. Use the list endpoint with ?all=true to see valid ids.')
    if not obj.is_active:
        when = getattr(obj, 'deleted_at', None)
        msg = f'{label} {pk} is currently inactive (soft-deleted)' + (f' since {when:%d %b %Y, %H:%M}.' if when else '.')
        hint = (f'Restore it with {restore_hint}.' if restore_hint
                else 'It cannot be read or edited, and it has no restore option.')
        raise APIError(msg, status_code=404, hint=hint)
    return obj

def fetch_visible(model, visible_qs, pk, label, restore_hint=None):
    """Pehle dekho ye record is user ko dikhna chahiye. Nahi to 404 (existence leak nahi hota)."""
    if not visible_qs.filter(pk=pk).exists():
        raise APIError(
            f'{label} with id {pk} is not available. It was never created, or you do not have access to it.',
            status_code=404,
            hint='Use the list endpoint to see the records you can access.')
    return fetch_active(model, pk, label, restore_hint)


def apply_active_filter(request, queryset):
    """?all=true / ?is_active=false sirf Super Admin, Admin, Manager ke liye. Baaki ko sirf active records."""
    if not can_see_inactive(request.user):
        return queryset.filter(is_active=True)
    if request.query_params.get('all') == 'true':
        return queryset
    if request.query_params.get('is_active') == 'false':
        return queryset.filter(is_active=False)
    return queryset.filter(is_active=True)
  
TASK_PRIORITIES = ['Low', 'Medium', 'High'] 

HARD_DELETE_ROLES = ('Super Admin',)    # only these roles may permanently delete users and projects

# A profile in this list can be given, changed or removed only by the roles listed for it
PROTECTED_PROFILES = {
    'Super Admin': ('Super Admin',),
    'Admin': ('Super Admin', 'Admin'),
    'Client': ('Super Admin', 'Admin'),
}


def check_profile_assignable(request, new_profile):
    """Blocks e.g. HR from giving the Super Admin or Admin profile."""
    allowed = PROTECTED_PROFILES.get(new_profile.name) if new_profile else None
    if allowed and role_of(request.user) not in allowed:
        raise APIError(f"Only a {' or '.join(allowed)} can give the '{new_profile.name}' profile.",
                       status_code=403, hint='Ask a Super Admin to do this.')


def check_can_manage_user(request, target, action='change'):
    """Blocks e.g. HR from changing, deleting or restoring a Super Admin or Admin user."""
    allowed = PROTECTED_PROFILES.get(role_of(target))
    if allowed and role_of(request.user) not in allowed:
        raise APIError(f"Only a {' or '.join(allowed)} can {action} a user with the '{role_of(target)}' profile.",
                       status_code=403, hint='Ask a Super Admin to do this.')


def check_not_self(request, target, action):
    if target.pk == request.user.pk:
        raise APIError(f'You cannot {action} your own account.', status_code=403,
                       hint='Ask another Super Admin or Admin to do this.')

def query_int(request, param):
    value = request.query_params.get(param)
    if value in (None, ''):
        return None
    if not value.isdigit():
        raise APIError(f"?{param} must be a whole number, for example ?{param}=7. You sent '{value}'.")
    return int(value)

def query_choice(request, param, allowed):
    value = request.query_params.get(param)
    if value and value.lower() not in [a.lower() for a in allowed]:
        raise APIError(f"'{value}' is not a valid value for ?{param}.",
                       hint=f"Allowed values: {', '.join(allowed)}.")
    return value

def query_lookup(request, param, category):
    """?status= / ?type= ko lookup table se check karta hai, galat par suggestion deta hai."""
    value = request.query_params.get(param)
    if not value:
        return None
    value = value.strip()
    if not LookupValue.objects.filter(category=category, name__iexact=value).exists():
        names = list(LookupValue.objects.filter(category=category).values_list('name', flat=True))
        close = suggest_value(value, names)
        msg = f"'{value}' is not a valid value for ?{param}."
        if close:
            msg += f" Did you mean '{close}'?"
        raise APIError(msg, hint=f"Allowed values: {', '.join(names) or 'none'}.")
    return value

def query_bool(request, param):
    value = request.query_params.get(param)
    if value and value.lower() not in ('true', 'false'):
        raise APIError(f"?{param} must be true or false. You sent '{value}'.")
    return value.lower() if value else None

def apply_search(queryset, search, fields):
    """'john sharma' jaise multi-word search ko har word par fields mein dhundhta hai."""
    if not search:
        return queryset
    for term in search.split():
        q = Q()
        for field in fields:
            q |= Q(**{f'{field}__icontains': term})
        queryset = queryset.filter(q)
    return queryset

# ==========================================
# USER VIEWS (APIView)
# ==========================================

class UserListCreateView(APIView):
    """
    GET  /api/users/           -> Active users list (Paginated)
    GET  /api/users/?status=inactive -> Inactive users list
    GET  /api/users/?status=all      -> All users list
    POST /api/users/           -> Register/Create new user
    """
    permission_classes = [UserWritePermission]

    def get(self, request):
        status_param = request.query_params.get('status')
        if status_param == 'inactive':
            users = User.objects.filter(status='Inactive').order_by('-id')
        elif status_param == 'all':
            users = User.objects.all().order_by('-id')
        else:
            users = User.objects.filter(status='Active').order_by('-id')

        users = apply_search(users, request.query_params.get('search'),
                             ['first_name', 'last_name', 'email', 'username', 'phone'])
        profile = request.query_params.get('profile')
        if profile:
            users = users.filter(profiles__name__iexact=profile)
        nationality = request.query_params.get('nationality')
        if nationality:
            users = users.filter(nationality__iexact=nationality)
 
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(users, request)
        serializer = UserSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        check_profile_assignable(request, serializer.validated_data.get('profiles'))
        user = serializer.save(created_by=request.user)
        send_welcome_email(user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    """
    GET    /api/users/<id>/ -> Retrieve single user
    PATCH  /api/users/<id>/ -> Partial update user
    PUT    /api/users/<id>/ -> Full update user
    DELETE /api/users/<id>/ -> Soft delete user (status = Inactive)
    DELETE /api/users/<id>/?hard=true -> Permanent delete
    """
    permission_classes = [UserWritePermission]

    def get_object(self, pk):
        return fetch_active(User, pk, 'User', f'PUT /api/users/{pk}/restore/')

    def get(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserSerializer(user).data)

    def patch(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        check_can_manage_user(request, user)
        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        check_profile_assignable(request, serializer.validated_data.get('profiles'))
        serializer.save(modified_by=request.user)
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        check_can_manage_user(request, user, 'delete')
        check_not_self(request, user, 'delete')
        if request.query_params.get('hard') == 'true':
            if role_of(request.user) not in HARD_DELETE_ROLES:
                raise APIError('Only a Super Admin can permanently delete a user.', status_code=403,
                               hint='Use DELETE without ?hard=true to deactivate the user instead.')
            user.delete()
            return Response({'message': 'User permanently deleted'}, status=status.HTTP_200_OK)

        user.status = 'Inactive'
        user.deleted_at = timezone.now()
        user.deleted_by = request.user
        user.is_active = False
        user.save()
        return Response({'message': 'User has been deleted.',
                         'hint': f'It can be restored with PUT /api/users/{pk}/restore/.'},
                        status=status.HTTP_200_OK)


class UserActivateView(APIView):
    """
    POST /api/users/<id>/activate/ -> Inactive user ko wapas Active banana
    """
    permission_classes = [UserWritePermission]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        check_can_manage_user(request, user, 'activate')      
        if user.is_active and user.status == 'Active':
            return Response({'error': f'User {user.email} is already active'},
                            status=status.HTTP_400_BAD_REQUEST)

        user.status = 'Active'
        user.is_active = True
        user.save()
        return Response({'message': f'User {user.email} is now Active!'}, status=status.HTTP_200_OK)


class UserDeactivateView(APIView):
    """
    POST /api/users/<id>/deactivate/ -> Change the user’s status to inactive
    """
    permission_classes = [UserWritePermission]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)     
        check_can_manage_user(request, user, 'deactivate')
        check_not_self(request, user, 'deactivate')
        if not user.is_active and user.status == 'Inactive':
            return Response({'error': f'User {user.email} is already inactive'},
                            status=status.HTTP_400_BAD_REQUEST)

        user.status = 'Inactive'
        user.deleted_at = timezone.now()
        user.deleted_by = request.user
        user.is_active = False
        user.save()
        return Response({'message': f'User {user.email} has been deactivated!'}, status=status.HTTP_200_OK)


 
# ==========================================
# AUTH VIEWS (APIView)
# ==========================================

def get_active_user(email):
    return User.objects.filter(email=email, status='Active').first()


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        login_serializer = LoginSerializer(data=request.data)
        login_serializer.is_valid(raise_exception=True)
        email = login_serializer.validated_data['email'].lower().strip()
        check_login_lock(email)                                    # 429 while this email is locked
        user = get_active_user(login_serializer.validated_data['email'])
        if not user or not user.check_password(login_serializer.validated_data['password']):
            record_login_failure(email)                            # count the wrong attempt
            raise AuthenticationFailed('Invalid email or password.')
        cache.delete(f'login_fail:{email}')                        # correct login: reset the counter
        refresh = RefreshToken.for_user(user)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])     # record when the user last logged in
        return Response({
            'message': 'You have successfully logged in.',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'role': role_of(user),
            },
        })

class MeView(APIView):
    """GET /api/auth/me/ -> Logged-in user's details and role."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class HealthView(APIView):
    """GET /api/health/ -> Server is running (used by Render / monitoring)."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'status': 'ok'})

# users/views.py

class SendOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        send_otp_serializer = SendOTPSerializer(data=request.data)
        # If the limit is exceeded, a ValidationError will be raised here
        send_otp_serializer.is_valid(raise_exception=True)
        
        user = get_active_user(send_otp_serializer.validated_data['email'])
        if user:
            # Increment the attempt count when the operation is successful.
            send_otp_serializer.record_attempt()
            create_and_send_otp(user, 'verify')
            
        return Response({'message': 'If the email exists, an OTP has been sent'})



class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        verify_otp_serializer = VerifyOTPSerializer(data=request.data)
        verify_otp_serializer.is_valid(raise_exception=True)
        user = get_active_user(verify_otp_serializer.validated_data['email'])
        if not user or not verify_otp(user, verify_otp_serializer.validated_data['otp'], 'verify'):
            raise APIError('Invalid or expired OTP.',
               hint='An OTP is valid for 5 minutes and works only once. Request a new one and try again.')
        return Response({'message': 'OTP verified'})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        forgot_password_serializer = ForgotPasswordSerializer(data=request.data)
        forgot_password_serializer.is_valid(raise_exception=True)
        user = get_active_user(forgot_password_serializer.validated_data['email'])
        if user:
            forgot_password_serializer.record_attempt()  # <-- Attempt count is recorded.
            create_and_send_otp(user, 'reset')
        return Response({'message': 'If the email exists, a reset OTP has been sent'})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        reset_password_serializer = ResetPasswordSerializer(data=request.data)
        reset_password_serializer.is_valid(raise_exception=True)
        user = get_active_user(reset_password_serializer.validated_data['email'])
        if not user or not verify_otp(user, reset_password_serializer.validated_data['otp'], 'reset'):
             raise APIError('Invalid or expired OTP.',
                           hint='An OTP is valid for 5 minutes and works only once. Request a new one and try again.')
        user.set_password(reset_password_serializer.validated_data['new_password'])
        user.save()
        return Response({'message': 'Password reset successful'})

# ==========================================
# PROFILE VIEWS (APIView)
# ==========================================

class ProfileListCreateView(APIView):
    """
    GET  /api/profiles/  -> List all profiles
    POST /api/profiles/  -> Create new profile
    """
    permission_classes = [ProfileWritePermission]

    def get(self, request):
        profiles = Profile.objects.all().order_by('name')
        serializer = ProfileSerializer(profiles, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(created_by=request.user)
        return Response(ProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class ProfileDetailView(APIView):
    """
    GET    /api/profiles/<id>/ -> Single profile
    PATCH  /api/profiles/<id>/ -> Partial update
    PUT    /api/profiles/<id>/ -> Full update
    DELETE /api/profiles/<id>/ -> Hard delete
    """
    permission_classes = [ProfileWritePermission]

    def get_object(self, pk):
        if pk < 1:
            raise APIError(f'Profile id {pk} is not valid. IDs start from 1.',
                           status_code=404, hint='Use GET /api/profiles/ to see valid ids.')
        obj = Profile.objects.filter(pk=pk).first()
        if obj is None:
            raise APIError(f'Profile with id {pk} is not available. It was never created, or it was permanently deleted.',
                           status_code=404, hint='Use GET /api/profiles/ to see valid ids.')
        return obj

    def get(self, request, pk):
        profile = self.get_object(pk)
        return Response(ProfileSerializer(profile).data)

    def patch(self, request, pk):
        profile = self.get_object(pk)
        if not profile:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        if profile.is_default:
            return Response({'error': 'Default profile cannot be updated'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(modified_by=request.user)
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        profile = self.get_object(pk)
        if not profile:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        if profile.is_default:
            return Response({'error': 'Default profile cannot be deleted'}, status=status.HTTP_403_FORBIDDEN)
        profile.delete()
        return Response({'message': 'Profile deleted. Users using it now have no profile.'}, status=status.HTTP_200_OK)


# ==========================================
# RESTORE VIEWS
# ==========================================

class ProjectRestoreView(APIView):
    """POST /api/projects/<id>/restore/ -> Soft-deleted project ko wapas active karna"""
    permission_classes = [ProjectWritePermission]

    def post(self, request, pk):
        try:
            project = visible_projects(request.user).get(pk=pk)    # sirf wahi jo is user ko dikhta hai
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        if project.is_active:
            return Response({'error': 'Project is already active'}, status=status.HTTP_400_BAD_REQUEST)

        project.is_active = True
        project.deleted_at = None
        project.deleted_by = None
        project.restored_at = timezone.now()
        project.restored_by = request.user
        project.save()
        log_activity(request.user, 'restored', f'Restored project "{project.title}"', project=project)
        return Response({
            'message': 'Project restored successfully',
            'project': ProjectSerializer(project, context={'request': request, 'include_attachments': True}).data
        }, status=status.HTTP_200_OK)


class ClientRestoreView(APIView):
    """POST /api/clients/<id>/restore/ -> Soft-deleted client ko wapas active karna"""
    permission_classes = [ClientWritePermission]

    def post(self, request, pk):
        try:
            client = Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)
        if client.is_active:
            return Response({'error': 'Client is already active'}, status=status.HTTP_400_BAD_REQUEST)

        client.is_active = True
        client.deleted_at = None
        client.deleted_by = None
        client.restored_at = timezone.now()
        client.restored_by = request.user
        client.save()
        return Response({
            'message': 'Client restored successfully',
            'client': ClientSerializer(client).data
        }, status=status.HTTP_200_OK)


class UserRestoreView(APIView):
    """PUT /api/users/<id>/restore/. -> Soft-deleted user ko wapas active karna"""
    permission_classes = [UserWritePermission]

    def put(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        check_can_manage_user(request, user, 'restore')     # 'deactivate' in the deactivate view, 'restore' in restore
        if user.is_active and user.status == 'Active':
            return Response({'error': 'User is already active'}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = True
        user.status = 'Active'
        user.deleted_at = None
        user.deleted_by = None
        user.modified_by = request.user
        user.save()
        return Response({
            'message': f'User {user.email} restored successfully',
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


# ==========================================
# CLIENT VIEWS (APIView)
# ==========================================

class ClientListCreateView(APIView):
    """
    GET  /api/clients/              -> Active clients list (Paginated)
    GET  /api/clients/?is_active=false -> Inactive clients list
    GET  /api/clients/?all=true     -> All clients list
    POST /api/clients/              -> Create new client
    """
    permission_classes = [ClientWritePermission]

    def get(self, request):
        if request.query_params.get('all') == 'true':
            clients = Client.objects.all().order_by('-id')
        elif request.query_params.get('is_active') == 'false':
            clients = Client.objects.filter(is_active=False).order_by('-id')
        else:
            clients = Client.objects.filter(is_active=True).order_by('-id')

        clients = apply_search(clients, request.query_params.get('search'),
                               ['first_name', 'last_name', 'email_id', 'contact_no', 'countries'])
        country = request.query_params.get('country')
        if country:
            clients = clients.filter(countries__iexact=country)

        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(clients, request)
        serializer = ClientSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = ClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = serializer.save(created_by=request.user)   # it would be saved logged in user
        return Response(ClientSerializer(client).data, status=status.HTTP_201_CREATED)


class ClientDetailView(APIView):
    """
    GET    /api/clients/<id>/ -> Retrieve single client
    PATCH  /api/clients/<id>/ -> Partial update client
    PUT    /api/clients/<id>/ -> Full update client
    DELETE /api/clients/<id>/ -> Soft delete client (is_active = False)
    DELETE /api/clients/<id>/?hard=true -> Permanent delete
    """
    permission_classes = [ClientWritePermission]

    def get_object(self, pk):
        return fetch_active(Client, pk, 'Client', f'POST /api/clients/{pk}/restore/')

    def get(self, request, pk):
        client = self.get_object(pk)
        if not client:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ClientSerializer(client).data)

    def patch(self, request, pk):
        client = self.get_object(pk)
        if not client:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ClientSerializer(client, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(modified_by=request.user)            # Which user updated and saved it ?
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        client = self.get_object(pk)
        if not client:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.query_params.get('hard') == 'true':
            if role_of(request.user) not in HARD_DELETE_ROLES:
                raise APIError('Only a Super Admin can permanently delete a client.', status_code=403)
            client.delete()
            return Response({'message': 'Client permanently deleted'}, status=status.HTTP_200_OK)
        # Soft delete tracking
        client.is_active = False
        client.deleted_by = request.user    # Which user deleted it ?
        client.deleted_at = timezone.now()  # At what time was it deleted ?
        client.save()
        return Response({'message': 'Client has been deleted.',
                         'hint': f'It can be restored with POST /api/clients/{pk}/restore/.'},
                        status=status.HTTP_200_OK)


class ClientActivateView(APIView):
    """
    POST /api/clients/<id>/activate/ ->  Make an inactive client active again
    """
    permission_classes = [ClientWritePermission]

    def post(self, request, pk):
        try:
            client = Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)
        if client.is_active:
            return Response({'error': f'Client {client.first_name} is already active'},
                            status=status.HTTP_400_BAD_REQUEST)

        client.is_active = True
        client.save()
        return Response({'message': f'Client {client.first_name} is now Active!'}, status=status.HTTP_200_OK)


class ClientDeactivateView(APIView):
    """
    POST /api/clients/<id>/deactivate/ -> Client ko Inactive karna
    """
    permission_classes = [ClientWritePermission]

    def post(self, request, pk):
        try:
            client = Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)
        if not client.is_active:
            return Response({'error': f'Client {client.first_name} is already inactive'},
                            status=status.HTTP_400_BAD_REQUEST)

        client.is_active = False
        client.save()
        return Response({'message': f'Client {client.first_name} has been deactivated!'}, status=status.HTTP_200_OK)

# ==========================================
# PROJECT VIEWS (APIView)
# ==========================================

class ProjectListCreateView(APIView):
    """
    GET  /api/projects/             -> Active projects list (Paginated)
    GET  /api/projects/?is_active=false -> Soft-deleted projects list
    GET  /api/projects/?all=true    -> All projects
    POST /api/projects/             -> Create new project (Authenticated)
    """
    permission_classes = [ProjectWritePermission]
    @extend_schema(responses=ProjectSerializer(many=True))
    def get(self, request):
        projects = apply_active_filter(
            request, visible_projects(request.user).prefetch_related('attachments', 'team_leaders__profiles').order_by('-id'))
        projects = apply_search(projects, request.query_params.get('search'),
                                ['title', 'type__name', 'description', 'client__first_name', 'client__last_name',
                                 'assigned_manager__first_name', 'assigned_manager__last_name'])
        status_value = query_lookup(request, 'status', 'project_status')
        if status_value:
            projects = projects.filter(status__name__iexact=status_value)
        type_value = query_lookup(request, 'type', 'project_type')
        if type_value:
            projects = projects.filter(type__name__iexact=type_value)

        client_id = query_int(request, 'client')
        if client_id:
            projects = projects.filter(client_id=client_id)
        manager_id = query_int(request, 'manager')
        if manager_id:
            projects = projects.filter(assigned_manager_id=manager_id)

        has_tasks = query_bool(request, 'has_tasks')
        if has_tasks == 'true':
            projects = projects.filter(tasks__is_active=True).distinct()
        elif has_tasks == 'false':
            projects = projects.exclude(tasks__is_active=True)

        task_user = query_int(request, 'task_assigned_to')
        if task_user:
            projects = projects.filter(tasks__assigned_to_id=task_user, tasks__is_active=True).distinct()
        
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(projects, request)
        serializer = ProjectSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)
    
    @extend_schema(request=ProjectSerializer, responses=ProjectSerializer)
    def post(self, request):
        serializer = ProjectSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project = serializer.save(created_by=request.user)
        log_activity(request.user, 'created', f'Created project "{project.title}"', project=project)
        send_project_created_emails(project)
        return Response(
            ProjectSerializer(project, context={'request': request, 'include_attachments': True}).data,
            status=status.HTTP_201_CREATED
        )

class ProjectDetailView(APIView):
    """
    GET    /api/projects/<id>/ -> Retrieve single project
    PATCH  /api/projects/<id>/ -> Partial update project
    PUT    /api/projects/<id>/ -> Full update project
    DELETE /api/projects/<id>/ -> Soft delete (is_active = False)
    DELETE /api/projects/<id>/?hard=true -> Permanent delete
    """
    permission_classes = [ProjectWritePermission]

    def get_object(self, pk):
        return fetch_visible(Project, visible_projects(self.request.user), pk, 'Project',
                             f'POST /api/projects/{pk}/restore/')

    def get(self, request, pk):
        project = self.get_object(pk)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProjectSerializer(
                            project, context={'request': request, 'include_attachments': True}
                         ).data)

    @extend_schema(request=ProjectSerializer, responses=ProjectSerializer)
    def patch(self, request, pk):
        project = self.get_object(pk)
        before = project_snapshot(project)
        serializer = ProjectSerializer(project, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        new_manager = serializer.validated_data.get('assigned_manager', project.assigned_manager)
        if new_manager != project.assigned_manager and role_of(request.user) not in ('Super Admin', 'Admin'):
            raise APIError('Only a Super Admin or Admin can change the manager of a project.', status_code=403,
                           hint='Ask an Admin to reassign the manager.')
        project = serializer.save(modified_by=request.user)
        changes = describe_changes(before, project_snapshot(project))
        if changes:
            log_activity(request.user, 'updated', f'Updated project "{project.title}": ' + '; '.join(changes),
                         project=project)
        return Response(
            ProjectSerializer(project, context={'request': request, 'include_attachments': True}).data
        )

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        project = self.get_object(pk)

        if request.query_params.get('hard') == 'true':
            if role_of(request.user) not in HARD_DELETE_ROLES:
                raise APIError('Only a Super Admin can permanently delete a project.', status_code=403,
                               hint='Use DELETE without ?hard=true to soft-delete it.')
            project.delete()
            return Response({'message': 'Project permanently deleted'}, status=status.HTTP_200_OK)

        project.is_active = False
        project.deleted_by = request.user
        project.deleted_at = timezone.now()
        project.save()
        log_activity(request.user, 'deleted', f'Deleted project "{project.title}"', project=project)
        return Response({'message': 'Project has been deleted.',
                         'hint': f'It can be restored with POST /api/projects/{pk}/restore/.'},
                        status=status.HTTP_200_OK)


# ==========================================
# PROJECT TASK VIEWS
# ==========================================

TASK_CREATE_ROLES = ('Super Admin', 'Admin', 'Team Leader')              # who may create tasks
TASK_OVERRIDE_ROLES = ('Super Admin', 'Admin')                           # full control over every task
COMMENT_ROLES = ('Super Admin', 'Admin', 'Manager', 'Team Leader', 'Developer')
COMMENT_MODERATOR_ROLES = ('Super Admin', 'Admin', 'Manager', 'Team Leader')   # may delete anyone's comment


def can_manage_tasks(user):
    """May create tasks."""
    return role_of(user) in TASK_CREATE_ROLES


def can_modify_task(user, task):
    """May edit, delete or activate this particular task. A Manager only views and comments."""
    role = role_of(user)
    if role in TASK_OVERRIDE_ROLES:
        return True
    if role == 'Team Leader':
        return task.created_by_id == user.id     # a Team Leader manages only the tasks he created
    return False


def can_comment(user):
    return role_of(user) in COMMENT_ROLES




class ProjectTaskListCreateView(APIView):
    """
    GET  /api/projects/<project_id>/tasks/  -> Tasks of a project (?search=, ?status=, ?assigned_to=, ?is_active=false, ?all=true)
    POST /api/projects/<project_id>/tasks/  -> Create task (Manager / Team Leader only)
    """
    permission_classes = [IsAuthenticated]

    def get_project(self, project_id):
        return fetch_visible(Project, visible_projects(self.request.user), project_id, 'Project',
                             f'POST /api/projects/{project_id}/restore/')

    def get(self, request, project_id):
        project = self.get_project(project_id)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        tasks = apply_active_filter(
            request,
            visible_tasks(request.user).filter(project=project).select_related('project', 'assigned_to').order_by('-id'))

        tasks = apply_search(tasks, request.query_params.get('search'),
                             ['title', 'description', 'assigned_to__first_name', 'assigned_to__last_name'])
        status_value = query_lookup(request, 'status', 'task_status')
        if status_value:
            tasks = tasks.filter(status__name__iexact=status_value)
        priority = query_choice(request, 'priority', TASK_PRIORITIES)
        if priority:
            tasks = tasks.filter(priority__iexact=priority)
        assigned = query_int(request, 'assigned_to')
        if assigned:
            tasks = tasks.filter(assigned_to_id=assigned)

        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(tasks, request)
        serializer = ProjectTaskSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, project_id):
        if not can_manage_tasks(request.user):
            return Response({'error': "Only a Super Admin, Admin or Team Leader can create a project task."},
                            status=status.HTTP_403_FORBIDDEN)
        project = self.get_project(project_id)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProjectTaskSerializer(data=request.data, context={'request': request, 'project': project})
        serializer.is_valid(raise_exception=True)
        task = serializer.save(project=project, created_by=request.user)
        who = f" for {_person(task.assigned_to)['name']}" if task.assigned_to else ''
        log_activity(request.user, 'created', f'Created task "{task.title}"{who}', project=project, task=task)
        return Response(
            ProjectTaskSerializer(task, context={'request': request, 'include_comments': True}).data,
            status=status.HTTP_201_CREATED
        )


class TaskListView(APIView):
    """
    GET /api/tasks/ -> Tasks of all projects
        ?assigned_to=<id> or ?assigned_to=me, ?status=, ?priority=, ?project=<id>, ?search=, ?is_active=false, ?all=true
    Each role sees only the tasks allowed by users/access.py.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tasks = apply_active_filter(
            request, visible_tasks(request.user).select_related('project', 'assigned_to').order_by('-id'))

        if role_of(request.user) in ('Super Admin', 'Admin', 'Manager', 'Team Leader'):
            assigned = request.query_params.get('assigned_to')
            if assigned == 'me':
                assigned = str(request.user.id)
            if assigned and assigned.isdigit():
                tasks = tasks.filter(assigned_to_id=assigned)

        tasks = apply_search(tasks, request.query_params.get('search'),
                             ['title', 'description', 'project__title'])
         
        status_value = query_lookup(request, 'status', 'task_status')
        if status_value:
            tasks = tasks.filter(status__name__iexact=status_value)
        priority = query_choice(request, 'priority', TASK_PRIORITIES)
        if priority:
            tasks = tasks.filter(priority__iexact=priority)
        project_id = query_int(request, 'project')
        if project_id:
            tasks = tasks.filter(project_id=project_id)
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(tasks, request)
        return paginator.get_paginated_response(
            ProjectTaskSerializer(page, many=True, context={'request': request}).data)


class ProjectTaskDetailView(APIView):
    """
    GET    /api/tasks/<id>/ -> Task with its comments
    PATCH  /api/tasks/<id>/ -> Update (Manager/Team Leader: all fields, assigned user: status only)
    DELETE /api/tasks/<id>/ -> Soft delete (Manager / Team Leader only)
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return fetch_visible(ProjectTask, visible_tasks(self.request.user), pk, 'Task',f'PUT /api/tasks/{pk}/activate/')

    def get(self, request, pk):
        task = self.get_object(pk)
        if not task:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProjectTaskSerializer(task, context={'request': request, 'include_comments': True}).data)

    def patch(self, request, pk):
        task = self.get_object(pk)
        if not task:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)

        is_assignee = task.assigned_to_id == request.user.id
        is_manager = can_modify_task(request.user, task)
        if not (is_assignee or is_manager):
            raise APIError('You are not allowed to update this task.', status_code=403,
                           hint='Only the assigned user, an Admin, or the Team Leader who created it can update it.')
        if not is_manager and set(request.data.keys()) - {'status'}:
            raise APIError('You can only update the status of your task.', status_code=403,
                           hint='Send only {"status": "..."}.')

        before = task_snapshot(task)
        serializer = ProjectTaskSerializer(task, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        task = serializer.save(modified_by=request.user)
        changes = describe_changes(before, task_snapshot(task))
        if changes:
            log_activity(request.user, 'updated', f'Updated task "{task.title}": ' + '; '.join(changes),
                         project=task.project, task=task)
        return Response(ProjectTaskSerializer(task, context={'request': request, 'include_comments': True}).data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        task = self.get_object(pk)
        if not task:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        if not can_modify_task(request.user, task):
            return Response({'error': 'You are not allowed to delete this task.',
                             'hint': 'Only an Admin or the Team Leader who created it can delete it.'},
                            status=status.HTTP_403_FORBIDDEN)
        task.is_active = False
        task.deleted_at = timezone.now()
        task.deleted_by = request.user
        task.modified_by = request.user
        task.save()
        log_activity(request.user, 'deleted', f'Deleted task "{task.title}"', project=task.project, task=task)
        return Response({'message': 'Task has been deleted.',
                         'hint': f'It can be restored with PUT /api/tasks/{pk}/activate/.'},
                        status=status.HTTP_200_OK)

class ProjectTaskActivateView(APIView):
    """PUT /api/tasks/<id>/activate/ -> Soft-deleted task ko wapas active karna (Manager / Team Leader only)"""
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        task = visible_tasks(request.user).filter(pk=pk).select_related('project', 'assigned_to').first()
        if not task:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        if not can_modify_task(request.user, task):
            return Response({'error': 'You are not allowed to activate this task.'},
                            status=status.HTTP_403_FORBIDDEN)
        if task.is_active:
            return Response({'error': 'Task is already active'}, status=status.HTTP_400_BAD_REQUEST)
        if not task.project.is_active:
            return Response({'error': 'The project of this task is not active'}, status=status.HTTP_400_BAD_REQUEST)
        if ProjectTask.objects.filter(project=task.project, title__iexact=task.title, is_active=True).exists():
            return Response({'error': 'A task with this title already exists in this project.'},
                            status=status.HTTP_400_BAD_REQUEST)

        task.is_active = True
        task.deleted_at = None
        task.deleted_by = None
        task.modified_by = request.user
        task.save()
        log_activity(request.user, 'restored', f'Restored task "{task.title}"', project=task.project, task=task)
        return Response({
            'message': 'Task activated successfully',
            'task': ProjectTaskSerializer(task, context={'request': request, 'include_comments': True}).data
        }, status=status.HTTP_200_OK)

        
# ==========================================
# TASK COMMENT VIEWS
# ==========================================

class TaskCommentListCreateView(APIView):
    """
    GET  /api/tasks/<task_id>/comments/ -> Comments of a task
    POST /api/tasks/<task_id>/comments/ -> Add comment ((Manager / Team Leader / Developer))
    """
    permission_classes = [IsAuthenticated, IsNotClient]

    def get_task(self, task_id):
        return fetch_visible(ProjectTask, visible_tasks(self.request.user), task_id, 'Task',
                             f'PUT /api/tasks/{task_id}/activate/')

    def get(self, request, task_id):
        task = self.get_task(task_id)
        if not task:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        comments = task.comments.filter(is_active=True).select_related('user').order_by('-created_at')
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(comments, request)
        return paginator.get_paginated_response(TaskCommentSerializer(page, many=True).data)

    def post(self, request, task_id):
        task = self.get_task(task_id)
        if not task:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        # 'Only Manager, Team Leader and Developer can comment.
        if not can_comment(request.user):
            return Response({'error': 'You are not allowed to comment on this task.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = TaskCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(task=task, user=request.user, created_by=request.user)
        log_activity(request.user, 'commented', f'Commented on task "{task.title}"', project=task.project, task=task)
        return Response(TaskCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class TaskCommentDetailView(APIView):
    """
    GET    /api/comments/<id>/ -> Single comment
    PATCH  /api/comments/<id>/ -> Edit (only the author)
    DELETE /api/comments/<id>/ -> Soft delete (author or Manager / Team Leader)
    """
    permission_classes = [IsAuthenticated, IsNotClient]

    def get_object(self, pk):
        return fetch_visible(TaskComment, TaskComment.objects.filter(task__in=visible_tasks(self.request.user)),pk, 'Comment')

    def get(self, request, pk):
        comment = self.get_object(pk)
        if not comment:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(TaskCommentSerializer(comment).data)

    def patch(self, request, pk):
        comment = self.get_object(pk)
        if not comment:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        if comment.user_id != request.user.id:
            return Response({'error': 'Only the author can edit this comment.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = TaskCommentSerializer(comment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(modified_by=request.user)
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        comment = self.get_object(pk)
        if not comment:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        if comment.user_id != request.user.id and role_of(request.user) not in COMMENT_MODERATOR_ROLES:
            return Response({'error': 'You are not allowed to delete this comment.'}, status=status.HTTP_403_FORBIDDEN)
        comment.is_active = False
        comment.deleted_by = request.user
        comment.deleted_at = timezone.now()
        comment.save()
        return Response({'message': 'Comment deleted successfully'}, status=status.HTTP_200_OK)


# ==========================================
# LOOKUP VIEWS (project type, project status, task status)
# ==========================================

class LookupListCreateView(APIView):
    """
    GET  /api/lookups/                          -> all values (any logged-in user)
    GET  /api/lookups/?category=project_status  -> values of one category
    POST /api/lookups/                          -> add a value (Super Admin / Admin)
    """
    permission_classes = [ProfileWritePermission]   # same roles as profiles

    def get(self, request):
        categories = [c for c, _ in LookupValue.CATEGORY_CHOICES]
        category = query_choice(request, 'category', categories)
        values = LookupValue.objects.all()
        if category:
            values = values.filter(category=category.lower())
        return Response(LookupValueSerializer(values, many=True).data)

    def post(self, request):
        serializer = LookupValueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = serializer.save(created_by=request.user)
        return Response(LookupValueSerializer(value).data, status=status.HTTP_201_CREATED)


class LookupDetailView(APIView):
    """
    GET    /api/lookups/<id>/ -> single value
    PATCH  /api/lookups/<id>/ -> rename (not allowed for default values)
    DELETE /api/lookups/<id>/ -> delete (not allowed for default values or values in use)
    """
    permission_classes = [ProfileWritePermission]

    def get_object(self, pk):
        obj = LookupValue.objects.filter(pk=pk).first()
        if obj is None:
            raise APIError(f'Value with id {pk} is not available.',
                           status_code=404, hint='Use GET /api/lookups/ to see valid ids.')
        return obj

    def get(self, request, pk):
        return Response(LookupValueSerializer(self.get_object(pk)).data)

    def patch(self, request, pk):
        value = self.get_object(pk)
        if value.is_default:
            raise APIError('Default value cannot be updated.', status_code=403,
                           hint='Only values you added yourself can be renamed or deleted.')
        serializer = LookupValueSerializer(value, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(modified_by=request.user)
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        value = self.get_object(pk)
        if value.is_default:
            raise APIError('Default value cannot be deleted.', status_code=403,
                           hint='Only values you added yourself can be renamed or deleted.')
        try:
            value.delete()
        except ProtectedError:
            raise APIError(f"'{value.name}' is in use by projects or tasks, so it cannot be deleted.",
                           hint='Change those records to another value first, then delete this one.')
        return Response({'message': 'Value deleted'}, status=status.HTTP_200_OK)


# ==========================================
# TEAM LEADERS, TEAM VIEWS AND "MY WORK"
# ==========================================

TEAM_VIEW_ROLES = ('Super Admin', 'Admin', 'Manager')


def _person(user):
    return {'id': user.id, 'name': f'{user.first_name} {user.last_name}'.strip() or user.email}


def _project_head(project):
    return {'id': project.id, 'title': project.title,
            'status': project.status.name if project.status else None,
            'manager': _person(project.assigned_manager) if project.assigned_manager else None}


def _is_done(task):
    return 1 if (task.status and task.status.name == 'Completed') else 0


def _summary(tasks):
    done = sum(_is_done(t) for t in tasks)
    return {'tasks': len(tasks), 'completed': done,
            'progress_percent': round(done * 100 / len(tasks)) if tasks else 0}


def _team_tasks(queryset):
    """Adds related rows and active comments, so no query runs per task."""
    return queryset.select_related('assigned_to__profiles', 'created_by', 'status').prefetch_related(
        Prefetch('comments',
                 queryset=TaskComment.objects.filter(is_active=True).select_related('user').order_by('-created_at'),
                 to_attr='active_comments'))


def _task_row(task):
    last = task.active_comments[0] if task.active_comments else None
    return {
        'id': task.id, 'title': task.title,
        'status': task.status.name if task.status else None,
        'priority': task.priority, 'deadline_date': task.deadline_date,
        'comments_count': len(task.active_comments),
        'last_comment': ({'by': _person(last.user) if last.user else None, 'at': last.created_at}
                         if last else None),
    }


def _dev_entry(user, detailed):
    entry = {**_person(user), 'tasks': 0, 'by_status': {}}
    if detailed:
        entry['task_list'] = []
    return entry


def _add_task(entry, task):
    name = task.status.name if task.status else 'No status'
    entry['tasks'] += 1
    entry['by_status'][name] = entry['by_status'].get(name, 0) + 1
    if 'task_list' in entry:
        entry['task_list'].append(_task_row(task))


def build_team(project, tasks, detailed=True):
    """Team Leaders of a project, the Developers under each, and their tasks."""
    leaders = {u.id: {**_person(u), 'tasks': 0, 'completed': 0, 'developers': {}}
               for u in project.team_leaders.all()}
    direct, counted, developer_ids = {}, [], set()
    for t in tasks:
        dev = t.assigned_to
        if dev is None or role_of(dev) != 'Developer':
            continue
        owner = leaders.get(t.created_by_id)          # the Team Leader who created the task
        bucket = owner['developers'] if owner else direct
        _add_task(bucket.setdefault(dev.id, _dev_entry(dev, detailed)), t)
        counted.append(t)
        developer_ids.add(dev.id)
        if owner:
            owner['tasks'] += 1
            owner['completed'] += _is_done(t)
    return {
        'team_leaders': [{**l, 'developers': list(l['developers'].values())} for l in leaders.values()],
        'direct_developers': list(direct.values()),      # tasks created by an Admin, not by a Team Leader
        'summary': {'team_leaders': len(leaders), 'developers': len(developer_ids), **_summary(counted)},
    }


def build_work(target, viewer):
    """Work of a Team Leader or Developer, limited to what the viewer is allowed to see."""
    role = role_of(target)
    if role not in ('Team Leader', 'Developer'):
        raise APIError('The work view is available only for Team Leaders and Developers.')
    base = visible_tasks(viewer).filter(is_active=True)
    if role == 'Team Leader':
        projects = visible_projects(viewer).filter(is_active=True, team_leaders=target)
        base = base.filter(project__in=projects, created_by=target)
    else:
        base = base.filter(assigned_to=target)
        projects = visible_projects(viewer).filter(is_active=True, pk__in=base.values('project_id'))
    tasks = list(_team_tasks(base))
    grouped = {}
    for t in tasks:
        grouped.setdefault(t.project_id, []).append(t)

    rows = []
    for project in projects.select_related('assigned_manager', 'status'):
        project_tasks = grouped.get(project.id, [])
        item = {'project': _project_head(project), 'summary': _summary(project_tasks)}
        if role == 'Team Leader':
            devs = {}
            for t in project_tasks:
                if t.assigned_to and role_of(t.assigned_to) == 'Developer':
                    _add_task(devs.setdefault(t.assigned_to_id, _dev_entry(t.assigned_to, True)), t)
            item['developers'] = list(devs.values())
        else:
            item['tasks'] = [_task_row(t) for t in project_tasks]
        rows.append(item)
    return {'user': {**_person(target), 'role': role}, 'summary': _summary(tasks), 'projects': rows}


def check_team_access(request):
    if role_of(request.user) not in TEAM_VIEW_ROLES:
        raise APIError('Only a Super Admin, Admin or Manager can view project teams.', status_code=403)


class ProjectTeamLeaderView(APIView):
    """
    GET    /api/projects/<id>/team-leaders/            -> Team Leaders of the project
    POST   /api/projects/<id>/team-leaders/            -> add Team Leaders  {"team_leaders": [9, "neha@acme.com"]}
    DELETE /api/projects/<id>/team-leaders/<user_id>/  -> remove one Team Leader
    Allowed: Super Admin, Admin, and the Manager of that project.
    """
    permission_classes = [IsAuthenticated]

    def get_project(self, request, pk):
        if role_of(request.user) not in TEAM_VIEW_ROLES:
            raise APIError('Only a Super Admin, Admin or the project Manager can manage Team Leaders.',
                           status_code=403)
        return fetch_visible(Project, visible_projects(request.user), pk, 'Project',
                             f'POST /api/projects/{pk}/restore/')

    def get(self, request, pk):
        project = self.get_project(request, pk)
        return Response({'project': _project_head(project),
                         'team_leaders': [_person(u) for u in project.team_leaders.all()]})

    def post(self, request, pk):
        project = self.get_project(request, pk)
        serializer = TeamLeaderAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project.team_leaders.add(*serializer.validated_data['team_leaders'])
        project.modified_by = request.user
        project.save(update_fields=['modified_by', 'modified_at'])
        log_activity(request.user, 'assigned', 'Assigned Team Leader(s): ' + ', '.join(_person(u)['name'] for u in serializer.validated_data['team_leaders']), project=project)
        return Response({'message': 'Team Leaders assigned.',
                         'team_leaders': [_person(u) for u in project.team_leaders.all()]})

    def delete(self, request, pk, user_id):
        project = self.get_project(request, pk)
        leader = project.team_leaders.filter(pk=user_id).first()
        if leader is None:
            raise APIError(f'User {user_id} is not a Team Leader of this project.', status_code=404)
        if ProjectTask.objects.filter(project=project, created_by=leader, is_active=True).exists():
            raise APIError(f"{_person(leader)['name']} still has active tasks in this project.",
                           hint='Delete those tasks first, then remove the Team Leader.')
        project.team_leaders.remove(leader)
        log_activity(request.user, 'updated', f"Removed Team Leader {_person(leader)['name']}", project=project)
        return Response({'message': 'Team Leader removed.', 'id': user_id})


class ProjectTeamView(APIView):
    """GET /api/projects/<id>/team/ -> Team Leaders, Developers, their tasks, status and last comment."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        check_team_access(request)
        project = fetch_visible(Project, visible_projects(request.user), pk, 'Project',
                                f'POST /api/projects/{pk}/restore/')
        tasks = _team_tasks(ProjectTask.objects.filter(project=project, is_active=True))
        return Response({'project': _project_head(project), **build_team(project, tasks)})


class ProjectTeamOverviewView(APIView):
    """GET /api/projects/team-overview/ -> every visible project with a short team summary."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        check_team_access(request)
        projects = list(visible_projects(request.user).filter(is_active=True)
                        .select_related('assigned_manager', 'status').prefetch_related('team_leaders'))
        grouped = {}
        for t in _team_tasks(ProjectTask.objects.filter(project__in=projects, is_active=True)):
            grouped.setdefault(t.project_id, []).append(t)
        data = [{'project': _project_head(p), **build_team(p, grouped.get(p.id, []), detailed=False)}
                for p in projects]
        return Response({'count': len(data), 'projects': data})


class MyWorkView(APIView):
    """GET /api/me/work/ -> my own projects, developers (Team Leader) or tasks (Developer)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_work(request.user, request.user))


class UserWorkView(APIView):
    """GET /api/users/<id>/work/ -> work of a Team Leader or Developer, only inside the viewer's projects."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        check_team_access(request)
        target = fetch_active(User, pk, 'User', f'PUT /api/users/{pk}/restore/')
        return Response(build_work(target, request.user))

# ==========================================
# LOGIN LIMIT, LOGOUT, ACTIVITY LOG, TASK ATTACHMENTS
# ==========================================

LOGIN_MAX_ATTEMPTS = 5                # wrong passwords allowed
LOGIN_LOCK_SECONDS = 15 * 60          # how long the email stays locked


def check_login_lock(email):
    """Raises 429 while this email is locked."""
    unlock_at = cache.get(f'login_lock:{email}')
    if unlock_at:
        wait = int(unlock_at - time.time())
        if wait > 0:
            raise Throttled(wait=wait)


def record_login_failure(email):
    fail_key = f'login_fail:{email}'
    fails = cache.get(fail_key, 0) + 1
    if fails >= LOGIN_MAX_ATTEMPTS:
        cache.set(f'login_lock:{email}', time.time() + LOGIN_LOCK_SECONDS, timeout=LOGIN_LOCK_SECONDS)
        cache.delete(fail_key)
    else:
        cache.set(fail_key, fails, timeout=LOGIN_LOCK_SECONDS)


class LogoutView(APIView):
    """POST /api/auth/logout/ {"refresh": "<token>"} -> the refresh token stops working."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            raise APIError('Send the refresh token, for example {"refresh": "<token>"}.')
        try:
            token = RefreshToken(refresh)
            if str(token['user_id']) != str(request.user.id):
                raise APIError('This refresh token does not belong to you.', status_code=403)
            token.blacklist()
        except TokenError:
            raise APIError('This refresh token is invalid, expired or already logged out.')
        return Response({'message': 'Logged out successfully.'})


# ---- activity log ----

def log_activity(user, action, description, project=None, task=None):
    ActivityLog.objects.create(user=user, action=action, description=description[:500],
                               project=project, task=task)


def task_snapshot(task):
    return {
        'title': task.title,
        'status': task.status.name if task.status else None,
        'assigned to': _person(task.assigned_to)['name'] if task.assigned_to else None,
        'priority': task.priority,
        'start date': str(task.start_date) if task.start_date else None,
        'deadline': str(task.deadline_date) if task.deadline_date else None,
    }


def project_snapshot(project):
    return {
        'title': project.title,
        'status': project.status.name if project.status else None,
        'manager': _person(project.assigned_manager)['name'] if project.assigned_manager else None,
        'client': _person(project.client)['name'] if project.client else None,
        'completion date': str(project.date_of_completion) if project.date_of_completion else None,
    }


def describe_changes(before, after):
    """['status: Pending -> Completed', ...] for every value that changed."""
    return [f'{field}: {before[field]} -> {after[field]}' for field in before if before[field] != after[field]]


def _activity_page(request, logs):
    paginator = PageNumberPagination()
    paginator.page_size = 20
    page = paginator.paginate_queryset(logs.select_related('user'), request)
    rows = [{'id': a.id, 'action': a.action, 'description': a.description,
             'by': _person(a.user) if a.user else None, 'at': a.created_at} for a in page]
    return paginator.get_paginated_response(rows)


class ProjectActivityView(APIView):
    """GET /api/projects/<id>/activity/ -> timeline of the project and all its tasks (Super Admin, Admin, Manager)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        check_team_access(request)
        project = fetch_visible(Project, visible_projects(request.user), pk, 'Project',
                                f'POST /api/projects/{pk}/restore/')
        return _activity_page(request, ActivityLog.objects.filter(project=project))


class TaskActivityView(APIView):
    """GET /api/tasks/<id>/activity/ -> timeline of one task (anyone who can see the task, except a Client)."""
    permission_classes = [IsAuthenticated, IsNotClient]

    def get(self, request, pk):
        task = fetch_visible(ProjectTask, visible_tasks(request.user), pk, 'Task',
                             f'PUT /api/tasks/{pk}/activate/')
        return _activity_page(request, ActivityLog.objects.filter(task=task))


# ---- task attachments ----

MAX_FILES_PER_UPLOAD = 5
MAX_FILES_PER_TASK = 20


class TaskAttachmentListCreateView(APIView):
    """
    GET  /api/tasks/<id>/attachments/ -> files of the task
    POST /api/tasks/<id>/attachments/ -> upload files (form-data, key "files", up to 5 at a time)
    """
    permission_classes = [IsAuthenticated, IsNotClient]

    def get_task(self, request, task_id):
        return fetch_visible(ProjectTask, visible_tasks(request.user), task_id, 'Task',
                             f'PUT /api/tasks/{task_id}/activate/')

    def get(self, request, task_id):
        task = self.get_task(request, task_id)
        files = task.attachments.select_related('uploaded_by')
        return Response(TaskAttachmentSerializer(files, many=True, context={'request': request}).data)

    def post(self, request, task_id):
        task = self.get_task(request, task_id)
        files = request.FILES.getlist('files')
        if not files:
            raise APIError('Attach at least one file in the form-data field "files".',
                           hint='In Postman use Body > form-data, key "files", type File.')
        if len(files) > MAX_FILES_PER_UPLOAD:
            raise APIError(f'You can upload at most {MAX_FILES_PER_UPLOAD} files at a time.')
        if task.attachments.count() + len(files) > MAX_FILES_PER_TASK:
            raise APIError(f'A task can hold at most {MAX_FILES_PER_TASK} files.')
        for f in files:
            try:
                validate_single_file(f)             # size and extension rules, same as project files
            except DRFValidationError as exc:
                raise APIError(str(exc.detail[0]))
        created = [TaskAttachment.objects.create(task=task, file=f, file_name=f.name, uploaded_by=request.user)
                   for f in files]
        log_activity(request.user, 'attached', f'Attached {len(created)} file(s) to task "{task.title}"',
                     project=task.project, task=task)
        return Response({'message': f'{len(created)} file(s) uploaded.',
                         'attachments': TaskAttachmentSerializer(created, many=True,
                                                                 context={'request': request}).data},
                        status=status.HTTP_201_CREATED)


class TaskAttachmentDetailView(APIView):
    """DELETE /api/attachments/<id>/ -> permanently remove a file (uploader, Admin, or the Team Leader who created the task)."""
    permission_classes = [IsAuthenticated, IsNotClient]

    def delete(self, request, pk):
        attachment = (TaskAttachment.objects.filter(pk=pk, task__in=visible_tasks(request.user))
                      .select_related('task__project').first())
        if attachment is None:
            raise APIError(f'Attachment with id {pk} is not available, or you do not have access to it.',
                           status_code=404, hint='Use GET /api/tasks/<id>/attachments/ to see valid ids.')
        task = attachment.task
        if attachment.uploaded_by_id != request.user.id and not can_modify_task(request.user, task):
            raise APIError('You are not allowed to delete this file.', status_code=403,
                           hint='Only the uploader, an Admin or the Team Leader who created the task can delete it.')
        name = attachment.file_name
        attachment.file.delete(save=False)
        attachment.delete()
        log_activity(request.user, 'deleted', f'Deleted file "{name}" from task "{task.title}"',
                     project=task.project, task=task)
        return Response({'message': 'File deleted permanently.', 'id': pk})

# ==========================================
# DASHBOARD
# ==========================================

class DashboardView(APIView):
    """
    GET /api/dashboard/ -> summary counts, scoped to what this user can see.
    Admin/Super Admin: whole system. Manager: own projects. Team Leader/Developer: their own work.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        month_start = today.replace(day=1)

        projects = visible_projects(request.user).filter(is_active=True)
        tasks = visible_tasks(request.user).filter(is_active=True)

        project_status_counts = {}
        for row in projects.values('status__name').annotate(count=Count('id')):
            project_status_counts[row['status__name'] or 'No status'] = row['count']

        task_status_counts = {}
        for row in tasks.values('status__name').annotate(count=Count('id')):
            task_status_counts[row['status__name'] or 'No status'] = row['count']

        completed_this_month = tasks.filter(
            status__name='Completed', completion_date__gte=month_start, completion_date__lte=today
        ).count()
        overdue = tasks.filter(deadline_date__lt=today).exclude(status__name='Completed').count()

        return Response({
            'as_of': today,
            'projects': {'total': projects.count(), 'by_status': project_status_counts},
            'tasks': {
                'total': tasks.count(),
                'by_status': task_status_counts,
                'completed_this_month': completed_this_month,
                'overdue': overdue,
            },
        })