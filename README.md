# Custom User Management & Authentication API

Django REST Framework project with a custom `User` model (inherits `AbstractUser`), user CRUD with soft delete, JWT login, OTP verification, forgot/reset password, and welcome emails.

## Tech Stack

- Python 3.10+
- Django, Django REST Framework
- djangorestframework-simplejwt (JWT auth)
- Pillow (image upload)
- SQLite (default database)

## Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd user_management

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run migrations
python manage.py makemigrations
python manage.py migrate

# 5. (Optional) Create admin user
python manage.py createsuperuser

# 6. Start server
crS
```

Server runs at `http://127.0.0.1:8000/`

## Email Configuration

By default, emails are printed in the terminal (console backend), so no email setup is needed for testing.

To send real emails via Gmail, add this in `config/settings.py`:

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-google-app-password'
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
```

Use a Google App Password (not your normal password). Do not commit credentials to GitHub; keep them in a `.env` file.

OTP expiry is set by `OTP_EXPIRY_MINUTES` in `settings.py` (default: 5 minutes).

## API Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| POST | `/api/users/` | Create user (sends welcome email) | No |
| GET | `/api/users/` | List users | Yes |
| GET | `/api/users/{id}/` | Retrieve user | Yes |
| PATCH / PUT | `/api/users/{id}/` | Update user | Yes |
| DELETE | `/api/users/{id}/` | Soft delete (status = Inactive) | Yes |
| POST | `/api/auth/login/` | Login with email and password | No |
| POST | `/api/auth/send-otp/` | Send OTP to email | No |
| POST | `/api/auth/verify-otp/` | Verify OTP | No |
| POST | `/api/auth/forgot-password/` | Send password-reset OTP | No |
| POST | `/api/auth/reset-password/` | Reset password using OTP | No |

Protected endpoints need this header:

```
Authorization: Bearer <access_token>
```

## Sample Requests and Responses

### Create user
`POST /api/users/`
```json
{
    "first_name": "Keshav",
    "last_name": "Singh",
    "email": "keshav@example.com",
    "username": "keshav",
    "password": "StrongPass@123",
    "profiles": "Developer",
    "gender": "Male",
    "blood_group": "O+",
    "phone": "9999999999"
}
```
Response `201 Created` (password is never returned):
```json
{
    "id": 1,
    "first_name": "Keshav",
    "last_name": "Singh",
    "email": "keshav@example.com",
    "username": "keshav",
    "profiles": "Developer",
    "status": "Active"
}
```

### Login
`POST /api/auth/login/`
```json
{"email": "keshav@example.com", "password": "StrongPass@123"}
```
Response `200 OK`:
```json
{"access": "<jwt_access_token>", "refresh": "<jwt_refresh_token>"}
```
Invalid credentials return `401`:
```json
{"error": "Invalid credentials"}
```

### Send OTP
`POST /api/auth/send-otp/`
```json
{"email": "keshav@example.com"}
```
Response:
```json
{"message": "If the email exists, an OTP has been sent"}
```

### Verify OTP
`POST /api/auth/verify-otp/`
```json
{"email": "keshav@example.com", "otp": "123456"}
```
Response: `{"message": "OTP verified"}`. A wrong or expired OTP returns `400`.

### Forgot password
`POST /api/auth/forgot-password/`
```json
{"email": "keshav@example.com"}
```

### Reset password
`POST /api/auth/reset-password/`
```json
{"email": "keshav@example.com", "otp": "123456", "new_password": "NewStrong@456"}
```
Response: `{"message": "Password reset successful"}`

### Soft delete
`DELETE /api/users/1/`
```json
{"message": "User deactivated"}
```
The record stays in the database with `status = Inactive`, and that user can no longer log in.

## Notes

- Passwords are hashed using Django's password hashing.
- OTPs are stored hashed, expire after a set time, and can be used only once.
- OTP values and passwords are never returned in API responses.
- Postman collection is included in the `postman/` folder (if added).

## Project Structure

```
user_management/
├── config/        # project settings and main urls
├── users/         # custom User model, serializers, views, urls, utils
├── manage.py
├── requirements.txt
└── README.md
```