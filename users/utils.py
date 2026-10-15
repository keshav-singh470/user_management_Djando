import secrets
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from .models import OTP


def send_welcome_email(user):
    send_mail(
        'Welcome!',
        f'Hi {user.first_name or user.username}, your account has been created.',
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


def create_and_send_otp(user, purpose):
    OTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    code = f"{secrets.randbelow(10**6):06d}"
    OTP.objects.create(user=user, purpose=purpose, code_hash=make_password(code))
    send_mail(
        'Your OTP',
        f'Your OTP is {code}. It is valid for {settings.OTP_EXPIRY_MINUTES} minutes.',
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


def verify_otp(user, code, purpose):
    otp = OTP.objects.filter(user=user, purpose=purpose, is_used=False).order_by('-created_at').first()
    if not otp or otp.is_expired() or not check_password(code, otp.code_hash):
        return False
    otp.is_used = True
    otp.save()
    return True