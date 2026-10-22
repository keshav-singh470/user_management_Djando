import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.mail import send_mail


def send_welcome_email(user):
    name = user.first_name if user.first_name else user.username
    try:
        send_mail(
            'Welcome to our platform',
            f'Hello {name}, your account has been created successfully.',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
    except Exception as e:
        print(f"[Email Notice] It's not possible to welcome email ({e}), but it has been created.")



def otp_key(user, purpose):
    return f'otp:{purpose}:{user.id}'


def create_and_send_otp(user, purpose):
    code = f'{secrets.randbelow(10**6):06d}'
    print(f"[TESTING OTP]: {code}")
    
    # The hashed OTP is stored in the cache and is automatically deleted after it expires.
    # When a new OTP is generated, it overwrites the previous OTP.
    cache.set(otp_key(user, purpose), make_password(code), timeout=settings.OTP_EXPIRY_MINUTES * 60)
    
    try:
        send_mail(
            'Your OTP',
            f'Your OTP is {code}. It is valid for {settings.OTP_EXPIRY_MINUTES} minutes.',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
    except Exception as e:
        print(f"[OTP Email Notice] if is not possible to send otp email ({e}), at that time you can use it terminal otp.")



def verify_otp(user, code, purpose):
    key = otp_key(user, purpose)
    hashed_code = cache.get(key)
    if not hashed_code or not check_password(code, hashed_code):
        return False
    cache.delete(key)   # OTP is deleted after it is used once
    return True