from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q

from .models import User, Client, Project, Profile, ProjectTask, TaskComment
from .serializers import *
from .utils import create_and_send_otp, send_welcome_email, verify_otp, send_project_created_emails
from .permissions import (UserWritePermission, ProfileWritePermission,
                          ClientWritePermission, ProjectWritePermission, role_of)

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
        user = serializer.save()
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
        try:
            return User.objects.get(pk=pk, is_active=True)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserSerializer(user).data)

    def patch(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(modified_by=request.user)
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.query_params.get('hard') == 'true':
            user.delete()
            return Response({'message': 'User permanently deleted'}, status=status.HTTP_200_OK)

        user.status = 'Inactive'
        user.deleted_at = timezone.now()
        user.deleted_by = request.user
        user.is_active = False
        user.save()
        return Response({'message': 'User deactivated successfully (soft delete)'}, status=status.HTTP_200_OK)


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
        user = get_active_user(login_serializer.validated_data['email'])
        if not user or not user.check_password(login_serializer.validated_data['password']):
            return Response({'error': 'Invalid credentials'}, status=401)
        refresh = RefreshToken.for_user(user)
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh)})


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
            return Response({'error': 'Invalid or expired OTP'}, status=400)
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
            return Response({'error': 'Invalid or expired OTP'}, status=400)
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
        profile = serializer.save()
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
        try:
            return Profile.objects.get(pk=pk)
        except Profile.DoesNotExist:
            return None

    def get(self, request, pk):
        profile = self.get_object(pk)
        if not profile:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProfileSerializer(profile).data)

    def patch(self, request, pk):
        profile = self.get_object(pk)
        if not profile:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        if profile.is_default:
            return Response({'error': 'Default profile cannot be updated'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
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
            project = Project.objects.get(pk=pk)    # is_active filter nahi, kyunki deleted wala chahiye
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
        try:
            return Client.objects.get(pk=pk, is_active=True)
        except Client.DoesNotExist:
            return None

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
        serializer.save(updated_by=request.user)            # Which user updated and saved it ?
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        client = self.get_object(pk)
        if not client:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.query_params.get('hard') == 'true':
            client.delete()
            return Response({'message': 'Client permanently deleted'}, status=status.HTTP_200_OK)
        # Soft delete tracking
        client.is_active = False
        client.deleted_by = request.user    # Which user deleted it ?
        client.deleted_at = timezone.now()  # At what time was it deleted ?
        client.save()
        return Response({'message': 'Client deactivated successfully (soft delete)'}, status=status.HTTP_200_OK)


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

    def get(self, request):
        if request.query_params.get('all') == 'true':
            projects = Project.objects.all().prefetch_related('attachments').order_by('-id')
        elif request.query_params.get('is_active') == 'false':
            projects = Project.objects.filter(is_active=False).prefetch_related('attachments').order_by('-id')
        else:
            projects = Project.objects.filter(is_active=True).prefetch_related('attachments').order_by('-id')

        projects = apply_search(projects, request.query_params.get('search'),
                                ['title', 'type', 'description', 'client__first_name', 'client__last_name',
                                 'assigned_manager__first_name', 'assigned_manager__last_name'])
        for param, lookup in [('status', 'status__iexact'), ('type', 'type__iexact'),
                              ('client', 'client_id'), ('manager', 'assigned_manager_id')]:
            value = request.query_params.get(param)
            if value:
                if param in ('client', 'manager') and not value.isdigit():
                    continue
                projects = projects.filter(**{lookup: value})
        has_tasks = request.query_params.get('has_tasks')         # How many tasks are there in projects
        if has_tasks == 'true':
            projects = projects.filter(tasks__is_active=True).distinct()
        elif has_tasks == 'false':
            projects = projects.exclude(tasks__is_active=True)
        task_user = request.query_params.get('task_assigned_to')    # Which user has how many tasks in projects
        if task_user and task_user.isdigit():
            projects = projects.filter(tasks__assigned_to_id=task_user, tasks__is_active=True).distinct()
        
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(projects, request)
        serializer = ProjectSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = ProjectSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project = serializer.save(created_by=request.user)
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
        try:
            return Project.objects.get(pk=pk, is_active=True)
        except Project.DoesNotExist:
            return None

    def get(self, request, pk):
        project = self.get_object(pk)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProjectSerializer(
                            project, context={'request': request, 'include_attachments': True}
                         ).data)

    def patch(self, request, pk):
        project = self.get_object(pk)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProjectSerializer(project, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project = serializer.save(updated_by=request.user)
        return Response(
            ProjectSerializer(project, context={'request': request, 'include_attachments': True}).data
        )

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        project = self.get_object(pk)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        # Hard delete option:
        if request.query_params.get('hard') == 'true':
            project.delete()
            return Response({'message': 'Project permanently deleted'}, status=status.HTTP_200_OK)

        # Soft delete:
        project.is_active = False
        project.deleted_by = request.user
        project.deleted_at = timezone.now()
        project.save()
        return Response({'message': 'Project soft-deleted successfully'}, status=status.HTTP_200_OK)


# ==========================================
# PROJECT TASK VIEWS
# ==========================================

TASK_MANAGER_ROLES = ('Manager', 'Team Leader')
COMMENT_ROLES = ('Manager', 'Team Leader', 'Developer')


def can_manage_tasks(user):
    return role_of(user) in TASK_MANAGER_ROLES


def can_comment(user):
    return role_of(user) in COMMENT_ROLES




class ProjectTaskListCreateView(APIView):
    """
    GET  /api/projects/<project_id>/tasks/  -> Tasks of a project (?search=, ?status=, ?assigned_to=, ?is_active=false, ?all=true)
    POST /api/projects/<project_id>/tasks/  -> Create task (Manager / Team Leader only)
    """
    permission_classes = [IsAuthenticated]

    def get_project(self, project_id):
        return Project.objects.filter(pk=project_id, is_active=True).first()

    def get(self, request, project_id):
        project = self.get_project(project_id)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        tasks = ProjectTask.objects.filter(project=project).select_related('project', 'assigned_to').order_by('-id')
        if request.query_params.get('all') == 'true':
            pass
        elif request.query_params.get('is_active') == 'false':
            tasks = tasks.filter(is_active=False)
        else:
            tasks = tasks.filter(is_active=True)

        tasks = apply_search(tasks, request.query_params.get('search'),
                             ['title', 'description', 'assigned_to__first_name', 'assigned_to__last_name'])
        status_value = request.query_params.get('status')
        if status_value:
            tasks = tasks.filter(status__iexact=status_value)
        priority = request.query_params.get('priority')
        if priority:
            tasks = tasks.filter(priority__iexact=priority)
        assigned = request.query_params.get('assigned_to')
        if assigned and assigned.isdigit():
            tasks = tasks.filter(assigned_to_id=assigned)

        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(tasks, request)
        serializer = ProjectTaskSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, project_id):
        if not can_manage_tasks(request.user):
            return Response({'error': "Only a user with the 'Manager' or 'Team Leader' profile can create a project task."},
                            status=status.HTTP_403_FORBIDDEN)
        project = self.get_project(project_id)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProjectTaskSerializer(data=request.data, context={'request': request, 'project': project})
        serializer.is_valid(raise_exception=True)
        task = serializer.save(project=project, created_by=request.user)
        return Response(
            ProjectTaskSerializer(task, context={'request': request, 'include_comments': True}).data,
            status=status.HTTP_201_CREATED
        )


class TaskListView(APIView):
    """
    GET /api/tasks/ -> Tasks of all projects
        ?assigned_to=<id> or ?assigned_to=me, ?status=, ?priority=, ?project=<id>, ?search=, ?is_active=false, ?all=true
    Super Admin / Admin / Manager / Team Leader see all tasks. Other users see only their own tasks.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tasks = ProjectTask.objects.select_related('project', 'assigned_to').order_by('-id')
        if request.query_params.get('all') == 'true':
            pass
        elif request.query_params.get('is_active') == 'false':
            tasks = tasks.filter(is_active=False)
        else:
            tasks = tasks.filter(is_active=True)

        sees_all = request.user.is_superuser or role_of(request.user) in ('Super Admin', 'Admin', 'Manager', 'Team Leader')
        if sees_all:
            assigned = request.query_params.get('assigned_to')
            if assigned == 'me':
                assigned = str(request.user.id)
            if assigned and assigned.isdigit():
                tasks = tasks.filter(assigned_to_id=assigned)
        else:
            tasks = tasks.filter(assigned_to=request.user)

        tasks = apply_search(tasks, request.query_params.get('search'),
                             ['title', 'description', 'project__title'])
        for param, lookup in [('status', 'status__iexact'), ('priority', 'priority__iexact'), ('project', 'project_id')]:
            value = request.query_params.get(param)
            if value and not (param == 'project' and not value.isdigit()):
                tasks = tasks.filter(**{lookup: value})

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
        return ProjectTask.objects.filter(pk=pk, is_active=True).select_related('project', 'assigned_to').first()

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
        is_manager = can_manage_tasks(request.user)
        if not (is_assignee or is_manager):
            return Response({'error': 'You are not allowed to update this task.'}, status=status.HTTP_403_FORBIDDEN)
        if 'status' in request.data and not is_assignee:
            return Response({'error': 'Only the user assigned to this task can update its status.'},
                            status=status.HTTP_403_FORBIDDEN)
        if not is_manager and set(request.data.keys()) - {'status'}:
            return Response({'error': 'You can only update the status of your task.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProjectTaskSerializer(task, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        task = serializer.save(updated_by=request.user)
        return Response(ProjectTaskSerializer(task, context={'request': request, 'include_comments': True}).data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        task = self.get_object(pk)
        if not task:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_tasks(request.user):
            return Response({'error': "Only a user with the 'Manager' or 'Team Leader' profile can delete a project task."},
                            status=status.HTTP_403_FORBIDDEN)
        task.is_active = False
        task.updated_by = request.user
        task.save()
        return Response({'message': 'Task soft-deleted successfully'}, status=status.HTTP_200_OK)

class ProjectTaskActivateView(APIView):
    """PUT /api/tasks/<id>/activate/ -> Soft-deleted task ko wapas active karna (Manager / Team Leader only)"""
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        if not can_manage_tasks(request.user):
            return Response({'error': "Only a user with the 'Manager' or 'Team Leader' profile can activate a project task."},
                            status=status.HTTP_403_FORBIDDEN)
        task = ProjectTask.objects.filter(pk=pk).select_related('project', 'assigned_to').first()
        if not task:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        if task.is_active:
            return Response({'error': 'Task is already active'}, status=status.HTTP_400_BAD_REQUEST)
        if not task.project.is_active:
            return Response({'error': 'The project of this task is not active'}, status=status.HTTP_400_BAD_REQUEST)
        if ProjectTask.objects.filter(project=task.project, title__iexact=task.title, is_active=True).exists():
            return Response({'error': 'A task with this title already exists in this project.'},
                            status=status.HTTP_400_BAD_REQUEST)

        task.is_active = True
        task.updated_by = request.user
        task.save()
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
    permission_classes = [IsAuthenticated]

    def get_task(self, task_id):
        return ProjectTask.objects.filter(pk=task_id, is_active=True).first()

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
        comment = serializer.save(task=task, user=request.user)
        return Response(TaskCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class TaskCommentDetailView(APIView):
    """
    GET    /api/comments/<id>/ -> Single comment
    PATCH  /api/comments/<id>/ -> Edit (only the author)
    DELETE /api/comments/<id>/ -> Soft delete (author or Manager / Team Leader)
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return TaskComment.objects.filter(pk=pk, is_active=True).select_related('user', 'task').first()

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
        serializer.save()
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        comment = self.get_object(pk)
        if not comment:
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        if comment.user_id != request.user.id and not can_manage_tasks(request.user):
            return Response({'error': 'You are not allowed to delete this comment.'}, status=status.HTTP_403_FORBIDDEN)
        comment.is_active = False
        comment.deleted_by = request.user
        comment.deleted_at = timezone.now()
        comment.save()
        return Response({'message': 'Comment deleted successfully'}, status=status.HTTP_200_OK)