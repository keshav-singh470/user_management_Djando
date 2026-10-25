from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone


from .models import User, Client
from .serializers import *
from .utils import create_and_send_otp, send_welcome_email, verify_otp


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
    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        status_param = request.query_params.get('status')
        if status_param == 'inactive':
            users = User.objects.filter(status='Inactive').order_by('-id')
        elif status_param == 'all':
            users = User.objects.all().order_by('-id')
        else:
            users = User.objects.filter(status='Active').order_by('-id')

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
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return User.objects.get(pk=pk)
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
        serializer.save()
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
        user.is_active = False
        user.save()
        return Response({'message': 'User deactivated successfully (soft delete)'}, status=status.HTTP_200_OK)


class UserActivateView(APIView):
    """
    POST /api/users/<id>/activate/ -> Inactive user ko wapas Active banana
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        user.status = 'Active'
        user.is_active = True
        user.save()
        return Response({'message': f'User {user.email} is now Active!'}, status=status.HTTP_200_OK)


class UserDeactivateView(APIView):
    """
    POST /api/users/<id>/deactivate/ -> User ko Inactive karna
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        user.status = 'Inactive'
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
        # Agar limit cross hui hogi to yahi par ValidationError raise ho jayegi:
        send_otp_serializer.is_valid(raise_exception=True)
        
        user = get_active_user(send_otp_serializer.validated_data['email'])
        if user:
            # Success hone par attempt count badhao:
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
# CLIENT VIEWS (APIView)
# ==========================================

class ClientListCreateView(APIView):
    """
    GET  /api/clients/              -> Active clients list (Paginated)
    GET  /api/clients/?is_active=false -> Inactive clients list
    GET  /api/clients/?all=true     -> All clients list
    POST /api/clients/              -> Create new client
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.query_params.get('all') == 'true':
            clients = Client.objects.all().order_by('-id')
        elif request.query_params.get('is_active') == 'false':
            clients = Client.objects.filter(is_active=False).order_by('-id')
        else:
            clients = Client.objects.filter(is_active=True).order_by('-id')

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
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Client.objects.get(pk=pk)
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
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            client = Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)

        client.is_active = True
        client.save()
        return Response({'message': f'Client {client.first_name} is now Active!'}, status=status.HTTP_200_OK)


class ClientDeactivateView(APIView):
    """
    POST /api/clients/<id>/deactivate/ -> Client ko Inactive karna
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            client = Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            return Response({'error': 'Client not found'}, status=status.HTTP_404_NOT_FOUND)

        client.is_active = False
        client.save()
        return Response({'message': f'Client {client.first_name} has been deactivated!'}, status=status.HTTP_200_OK)


