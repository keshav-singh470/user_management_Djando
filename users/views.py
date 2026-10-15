from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import *
from .utils import create_and_send_otp, send_welcome_email, verify_otp


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-id')

    def get_serializer_class(self):
        return UserCreateSerializer if self.action == 'create' else UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        user = serializer.save()
        send_welcome_email(user)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        user.status = 'Inactive'          # soft delete
        user.save()
        return Response({'message': 'User deactivated'}, status=status.HTTP_200_OK)


def get_active_user(email):
    return User.objects.filter(email=email, status='Active').first()


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = get_active_user(s.validated_data['email'])
        if not user or not user.check_password(s.validated_data['password']):
            return Response({'error': 'Invalid credentials'}, status=401)
        refresh = RefreshToken.for_user(user)
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh)})


class SendOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = SendOTPSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = get_active_user(s.validated_data['email'])
        if user:
            create_and_send_otp(user, 'verify')
        return Response({'message': 'If the email exists, an OTP has been sent'})


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = VerifyOTPSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = get_active_user(s.validated_data['email'])
        if not user or not verify_otp(user, s.validated_data['otp'], 'verify'):
            return Response({'error': 'Invalid or expired OTP'}, status=400)
        return Response({'message': 'OTP verified'})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = ForgotPasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = get_active_user(s.validated_data['email'])
        if user:
            create_and_send_otp(user, 'reset')
        return Response({'message': 'If the email exists, a reset OTP has been sent'})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = ResetPasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = get_active_user(s.validated_data['email'])
        if not user or not verify_otp(user, s.validated_data['otp'], 'reset'):
            return Response({'error': 'Invalid or expired OTP'}, status=400)
        user.set_password(s.validated_data['new_password'])
        user.save()
        return Response({'message': 'Password reset successful'})