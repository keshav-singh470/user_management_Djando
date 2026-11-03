import secrets
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.mail import send_mail
from rest_framework import serializers
import logging
logger = logging.getLogger(__name__)
OTP_MAX_REQUESTS = 3
OTP_WINDOW_SECONDS = 12 * 60 * 60  # 12 hours = 43200 seconds

def check_and_increment_otp_limit(email):
    cache_key = f"otp_request_count:{email.lower()}"
    request_count = cache.get(cache_key)

    if request_count is not None and request_count >= OTP_MAX_REQUESTS:
        raise serializers.ValidationError(
            "You have exceeded the maximum number of OTP requests. Please try again after 12 hours."
        )

    if request_count is None:
        # First request in the 12-hour window
        cache.set(cache_key, 1, timeout=OTP_WINDOW_SECONDS)
    else:
        # Use INCR or SET while preserving the 12-hour TTL
        try:
            cache.incr(cache_key)
        except Exception:
            #Provide a safe fallback for InMemoryCache and other cache backends
            cache.set(cache_key, request_count + 1, timeout=OTP_WINDOW_SECONDS)



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

def _full_name(user):
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.username


def _send_project_mail(subject, body, to_email):
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email])
    except Exception:
        # Project ban chuka hai, isliye mail fail hone par API ko error mat do
        logger.exception("Could not send project email to %s", to_email)


def send_project_created_emails(project):
    manager = project.assigned_manager
    client = project.client
    base = (
        f"Project     : {project.title}\n"
        f"Status      : {project.status}\n"
        f"Description : {project.description or '-'}\n"
    )

    # 1) Client ko mail (project details + manager ki jaankari)
    if client and client.email_id:
        if manager:
            manager_info = f"Manager     : {_full_name(manager)} ({manager.email}, {manager.phone or '-'})\n"
        else:
            manager_info = "Manager     : Not assigned yet\n"
        _send_project_mail(
            f"New project created: {project.title}",
            f"Hello {client.first_name or 'Client'},\n\nA new project has been created for you.\n\n"
            f"{base}{manager_info}\nRegards,\nTeam",
            client.email_id,
        )

    # 2) Manager ko mail (project details + client ki jaankari)
    if manager and manager.email:
        if client:
            client_info = (
                f"Client      : {client.first_name or ''} {client.last_name or ''}".strip()
                + f" ({client.email_id or '-'}, {client.contact_no or '-'})\n"
            )
        else:
            client_info = "Client      : Not assigned\n"
        _send_project_mail(
            f"You are assigned to project: {project.title}",
            f"Hello {_full_name(manager)},\n\nYou have been assigned a new project.\n\n"
            f"{base}{client_info}\nRegards,\nTeam",
            manager.email,
        )