import logging

from django.conf import settings
from django.db import IntegrityError
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)
WRITE_METHODS = ('POST', 'PUT', 'PATCH')


class APIError(exceptions.APIException):
    """Views mein use karo: raise APIError('Project is already active', hint='...')"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'The request could not be completed.'
    default_code = 'api_error'

    def __init__(self, message=None, status_code=None, hint=None):
        super().__init__(message)
        if status_code:
            self.status_code = status_code
        self.hint = hint


DATE = 'Date in YYYY-MM-DD format, for example "2026-12-31".'

# Har field ka matlab: error aane par frontend developer ko yahi dikhega
FIELD_HELP = {
    'name': 'Text with at least one letter. Profile names: 2-50 characters. Status/type values: 2-100 characters. Example: "AI Developer" or "In Review".',
    'profiles': 'A profile id (for example 7) or an existing profile name such as "Manager". An unknown profile is rejected (create it first with POST /api/profiles/).',
    'email': 'A valid email address, for example "rahul.sharma@example.com".',
    'email_id': 'A valid and unique client email address.',
    'password': 'Text. Your account password.',
    'new_password': 'At least 8 characters. Not too common and not only digits.',
    'otp': 'Exactly 6 digits, for example "123456". It is sent by email, valid for 5 minutes and works only once.',
    'refresh': 'The refresh token you received from POST /api/auth/login/.',
    'first_name': 'Text, for example "Rahul".',
    'gender': 'One of: Male, Female, Other (any letter case).',
    'blood_group': 'One of: A+, A-, B+, B-, AB+, AB-, O+, O-.',
    'phone': 'Digits only, up to 15 characters.',
    'status': 'Project/task status. See the allowed values with GET /api/lookups/?category=project_status (or task_status). Users: Active, Inactive.',
    'priority': 'One of: Low, Medium, High (exact case).',
    'title': 'Text, up to 200 characters. Must be unique (projects: across all projects, tasks: inside the project).',
    'type': 'Project type. See the allowed values with GET /api/lookups/?category=project_type.',
    'client': 'User id or email of an active user whose profile is "Client".',
    'assigned_manager': 'User id or email of an active user whose profile is "Manager". Only a Super Admin or Admin can set or change it.',
    'assigned_to': 'User id or email of an active user whose profile is "Developer".',
    'date_of_completion': DATE,
    'start_date': DATE,
    'deadline_date': DATE + ' Must not be before start_date or after the project completion date.',
    'estimated_hours': 'Number up to 9999.99, for example 12 or 4.5.',
    'hours_spent': 'Number greater than 0 and up to 9999.99, for example 4.5.',
    'comment': 'Text. It cannot be blank.',
    'uploaded_files': 'Send as form-data (not JSON). Allowed: pdf, png, jpg, jpeg, doc, docx, xlsx, txt. Max 10 MB each.',
    'remove_attachment_ids': 'List of attachment ids (not the project id), for example 1.',
    'team_leaders': 'List of Team Leader user ids or emails, for example [9, "neha@acme.com"].',
}

_PROFILE = {'name': 'AI Developer'}
_USER = {'first_name': 'Rahul', 'last_name': 'Sharma', 'email': 'rahul.sharma@example.com', 'profiles': 'Developer'}
_CLIENT = {'first_name': 'Amar', 'email_id': 'amar.sharma@example.com', 'countries': 'India'}
_PROJECT = {'title': 'Cloud ERP System', 'type': 'Web App', 'client': 7,
            'assigned_manager': 24, 'date_of_completion': '2026-12-31'}
_TASK = {'title': 'Build login page', 'assigned_to': 'rahul.sharma@example.com',
         'start_date': '2026-11-06', 'deadline_date': '2026-11-20', 'priority': 'High'}
_COMMENT = {'comment': 'Login form done.', 'hours_spent': 4.5}
_EMAIL = {'email': 'user@example.com'}

# View ka class name -> us endpoint ki sahi body
REQUEST_EXAMPLES = {
    'LoginView': {'email': 'user@example.com', 'password': 'your_password'},
    'TokenRefreshView': {'refresh': '<your_refresh_token>'},
    'SendOTPView': _EMAIL,
    'ForgotPasswordView': _EMAIL,
    'VerifyOTPView': {'email': 'user@example.com', 'otp': '123456'},
    'ResetPasswordView': {'email': 'user@example.com', 'otp': '123456', 'new_password': 'NewStrongPass@123'},
    'ProfileListCreateView': _PROFILE,
    'ProfileDetailView': _PROFILE,
    'UserListCreateView': _USER,
    'UserDetailView': {'current_address': 'Noida Sector 62, UP'},
    'ClientListCreateView': _CLIENT,
    'ClientDetailView': {'contact_no': '9111111111'},
    'ProjectListCreateView': _PROJECT,
    'ProjectDetailView': {'status': 'In Progress', 'description': 'Updated scope'},
    'ProjectTaskListCreateView': _TASK,
    'ProjectTaskDetailView': {'priority': 'Medium', 'deadline_date': '2026-11-22'},
    'TaskCommentListCreateView': _COMMENT,
    'TaskCommentDetailView': {'comment': 'Updated comment'},
    'LookupListCreateView': {'category': 'project_status', 'name': 'In Review'},
    'LookupDetailView': {'name': 'In Review'},
    'ProjectTeamLeaderView': {'team_leaders': [9]},
    'LogoutView': {'refresh': '<your_refresh_token>'},
}


def _text(detail):
    if isinstance(detail, dict):
        detail = detail.get('detail', detail)
    return str(detail)


def custom_exception_handler(exc, context):
    view = context.get('view')
    request = context.get('request')
    view_name = view.__class__.__name__ if view else ''
    method = request.method if request else ''
    example = REQUEST_EXAMPLES.get(view_name) if method in WRITE_METHODS else None

    response = exception_handler(exc, context)

    # ---- DRF ne handle nahi kiya: database error ya code bug ----
    if response is None:
        if isinstance(exc, IntegrityError):
            return Response({
                'success': False, 'status_code': 409,
                'message': 'This data conflicts with an existing record.',
                'hint': 'A unique value (for example email or title) probably already exists. Change it and try again.',
            }, status=status.HTTP_409_CONFLICT)
        logger.error('Unhandled error in %s', view_name, exc_info=exc)
        body = {
            'success': False, 'status_code': 500,
            'message': 'Something went wrong on the server.',
            'hint': 'This is not your mistake. Please try again. If it keeps happening, contact the developer.',
        }
        if settings.DEBUG:
            body['debug'] = f'{type(exc).__name__}: {exc}'   # sirf local par dikhega
        return Response(body, status=500)

    code = response.status_code
    original = response.data
    hint = getattr(exc, 'hint', None)
    body = {'success': False, 'status_code': code}

    if isinstance(exc, exceptions.ParseError):
        body['message'] = 'The request body could not be read.'
        hint = hint or ('Send valid JSON with the header Content-Type: application/json. '
                        'Check for missing quotes, commas or brackets.')
        if example:
            body['example_request'] = example

    elif isinstance(exc, exceptions.ValidationError):
        errors = original if isinstance(original, dict) else {'non_field_errors': original}
        body['message'] = 'Validation failed. Please correct the errors below.'
        body['errors'] = errors
        field_help = {f: FIELD_HELP[f] for f in errors if f in FIELD_HELP}
        if field_help:
            body['field_help'] = field_help
        if example:
            body['example_request'] = example
        hint = hint or ('Each key in "errors" is a field name and its value says what to fix. '
                        '"field_help" shows the expected format.')

    elif code == 401:
        err_code = original.get('code') if isinstance(original, dict) else None
        if isinstance(exc, exceptions.NotAuthenticated):
            body['message'] = 'Authentication required. No access token was sent.'
            hint = ('Log in with POST /api/auth/login/, then send the header '
                    'Authorization: Bearer <access_token> with every request.')
        elif err_code == 'token_not_valid':
            body['message'] = 'Your access token is invalid or has expired.'
            hint = ('Access tokens last 30 minutes. Get a new one with POST /api/auth/refresh/ '
                    'and {"refresh": "<refresh_token>"}, or log in again.')
        else:
            body['message'] = _text(original)
            hint = hint or ('Check your email and password. For token errors the header must be exactly '
                            '"Authorization: Bearer <access_token>" (with one space).')

    elif code == 403:
        body['message'] = _text(original)
        hint = hint or 'Your role is not allowed to do this. Log in with a user that has the required role.'

    elif code == 404:
        body['message'] = _text(original)
        hint = hint or ('Check that the id is a real number and the record is not soft-deleted. Use the list '
                        'endpoint to find ids (add ?all=true or ?is_active=false to include deleted records).')

    elif code == 405:
        allowed = ', '.join(getattr(view, 'allowed_methods', []))
        body['message'] = f'{method} is not allowed on this URL.'
        hint = f'Allowed methods for this URL: {allowed}.'

    elif code == 415:
        body['message'] = 'Unsupported content type.'
        hint = 'Send JSON with Content-Type: application/json, or use form-data when uploading files.'

    elif code == 429:
        wait = getattr(exc, 'wait', None)
        body['message'] = 'Too many requests.'
        hint = f'Please try again after {int(wait)} seconds.' if wait else 'Please try again later.'

    else:                      # APIError (already active, invalid OTP, etc.)
        body['message'] = _text(original)

    if hint:
        body['hint'] = hint
    response.data = body
    return response