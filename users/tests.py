"""
Automatic check of the assignment requirements.

Place this file at users/tests.py (replace the default one) and run:
    python manage.py test users -v 2
"""
import re
import time
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from rest_framework.test import APITestCase

from .models import User
from .utils import otp_key

PASSWORD = "Keshav@12345"
NEW_PASSWORD = "NewPass@45678"


def make_user(email="keshav@example.com", username="keshav", **extra):
    return User.objects.create_user(
        username=username, email=email, password=PASSWORD,
        first_name="Keshav", last_name="Singh", **extra
    )


def last_otp_from_mail():
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


class ModelTests(APITestCase):
    def test_1_all_required_fields_exist(self):
        required = [
            "first_name", "last_name", "email", "username", "profiles",
            "date_of_birth", "gender", "nationality", "image", "blood_group",
            "phone", "permanent_address", "current_address",
            "emergency_contact_name", "emergency_contact_number",
            "emergency_contact_relationship", "status",
        ]
        for name in required:
            User._meta.get_field(name)  # raises FieldDoesNotExist if missing

    def test_2_choices_and_unique_email(self):
        self.assertTrue(User._meta.get_field("email").unique)
        profiles = [c[0] for c in User._meta.get_field("profiles").choices]
        for p in ["Administrator", "Standard", "Developer", "Client", "Human Resource"]:
            self.assertIn(p, profiles)
        status_vals = [c[0] for c in User._meta.get_field("status").choices]
        self.assertEqual(sorted(status_vals), ["Active", "Inactive"])


class UserCrudTests(APITestCase):
    payload = {
        "first_name": "Adarsh", "last_name": "Kumar",
        "email": "adarsh@example.com", "username": "adarsh",
        "password": PASSWORD, "profiles": "Developer",
        "gender": "Male", "blood_group": "O+", "phone": "9999999999",
    }

    def login_token(self, email="keshav@example.com", password=PASSWORD):
        r = self.client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
        return r.data["access"]

    def auth(self):
        make_user()
        token = self.login_token()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_create_user_ok_no_password_in_response(self):
        r = self.client.post("/api/users/", self.payload, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn("password", r.data)

    def test_create_user_sends_welcome_email(self):
        self.client.post("/api/users/", self.payload, format="json")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["adarsh@example.com"])

    def test_password_is_hashed_in_db(self):
        self.client.post("/api/users/", self.payload, format="json")
        user = User.objects.get(email="adarsh@example.com")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_create_validation_errors(self):
        bad = dict(self.payload)
        bad.pop("email")
        self.assertEqual(self.client.post("/api/users/", bad, format="json").status_code, 400)

    def test_duplicate_email_rejected(self):
        self.client.post("/api/users/", self.payload, format="json")
        again = dict(self.payload, username="another")
        self.assertEqual(self.client.post("/api/users/", again, format="json").status_code, 400)

    def test_weak_password_rejected(self):
        weak = dict(self.payload, password="1234")
        self.assertEqual(self.client.post("/api/users/", weak, format="json").status_code, 400)

    def test_list_requires_jwt(self):
        self.assertEqual(self.client.get("/api/users/").status_code, 401)
        self.auth()
        r = self.client.get("/api/users/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("password", str(r.data))

    def test_retrieve_user(self):
        self.auth()
        uid = User.objects.get(email="keshav@example.com").id
        r = self.client.get(f"/api/users/{uid}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["email"], "keshav@example.com")
        self.assertNotIn("password", r.data)

    def test_patch_and_put_update(self):
        self.auth()
        uid = User.objects.get(email="keshav@example.com").id
        r = self.client.patch(f"/api/users/{uid}/", {"phone": "8888888888"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["phone"], "8888888888")
        put = {"first_name": "K", "last_name": "S", "email": "keshav@example.com",
               "username": "keshav", "profiles": "Standard", "status": "Active"}
        r = self.client.put(f"/api/users/{uid}/", put, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_soft_delete_sets_inactive_and_keeps_record(self):
        self.auth()
        other = make_user(email="other@example.com", username="other")
        r = self.client.delete(f"/api/users/{other.id}/")
        self.assertIn(r.status_code, (200, 204))
        other.refresh_from_db()                      # record still exists
        self.assertEqual(other.status, "Inactive")

    def test_inactive_user_cannot_login(self):
        u = make_user()
        u.status = "Inactive"
        u.save()
        r = self.client.post("/api/auth/login/", {"email": u.email, "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 401)


class LoginTests(APITestCase):
    def test_login_returns_jwt(self):
        make_user()
        r = self.client.post("/api/auth/login/",
                             {"email": "keshav@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)

    def test_wrong_password_rejected(self):
        make_user()
        r = self.client.post("/api/auth/login/",
                             {"email": "keshav@example.com", "password": "wrong"}, format="json")
        self.assertEqual(r.status_code, 401)


class OTPTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()

    def send_otp(self):
        r = self.client.post("/api/auth/send-otp/", {"email": self.user.email}, format="json")
        self.assertEqual(r.status_code, 200)
        return r

    def test_send_otp_emails_code_and_hides_it_in_response(self):
        r = self.send_otp()
        code = last_otp_from_mail()
        self.assertNotIn(code, str(r.data))
        self.assertEqual(mail.outbox[-1].to, [self.user.email])

    def test_otp_is_stored_hashed(self):
        self.send_otp()
        code = last_otp_from_mail()
        stored = cache.get(otp_key(self.user, "verify"))
        self.assertIsNotNone(stored)
        self.assertNotEqual(stored, code)

    def test_otp_is_deleted_after_use(self):
        self.send_otp()
        code = last_otp_from_mail()
        self.client.post("/api/auth/verify-otp/", {"email": self.user.email, "otp": code}, format="json")
        self.assertIsNone(cache.get(otp_key(self.user, "verify")))

    def test_otp_of_one_purpose_cannot_be_used_for_another(self):
        self.send_otp()                                   # purpose: verify
        code = last_otp_from_mail()
        r = self.client.post("/api/auth/reset-password/",
                             {"email": self.user.email, "otp": code, "new_password": NEW_PASSWORD},
                             format="json")
        self.assertEqual(r.status_code, 400)

    def test_verify_otp_success_then_cannot_reuse(self):
        self.send_otp()
        code = last_otp_from_mail()
        body = {"email": self.user.email, "otp": code}
        self.assertEqual(self.client.post("/api/auth/verify-otp/", body, format="json").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/verify-otp/", body, format="json").status_code, 400)

    def test_verify_wrong_otp(self):
        self.send_otp()
        r = self.client.post("/api/auth/verify-otp/",
                             {"email": self.user.email, "otp": "000000"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_otp_expires(self):
        self.send_otp()
        code = last_otp_from_mail()
        # cache ki clock 30 minute aage kar do, OTP auto-expire ho chuka hoga
        with patch("django.core.cache.backends.locmem.time") as fake_time:
            fake_time.time.return_value = time.time() + 30 * 60
            r = self.client.post("/api/auth/verify-otp/",
                                 {"email": self.user.email, "otp": code}, format="json")
        self.assertEqual(r.status_code, 400)


class PasswordResetTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()

    def test_forgot_and_reset_password_flow(self):
        r = self.client.post("/api/auth/forgot-password/", {"email": self.user.email}, format="json")
        self.assertEqual(r.status_code, 200)
        code = last_otp_from_mail()
        self.assertNotIn(code, str(r.data))

        r = self.client.post("/api/auth/reset-password/",
                             {"email": self.user.email, "otp": code, "new_password": NEW_PASSWORD},
                             format="json")
        self.assertEqual(r.status_code, 200, r.data)

        ok = self.client.post("/api/auth/login/",
                              {"email": self.user.email, "password": NEW_PASSWORD}, format="json")
        old = self.client.post("/api/auth/login/",
                               {"email": self.user.email, "password": PASSWORD}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(old.status_code, 401)

    def test_reset_with_wrong_otp_fails(self):
        self.client.post("/api/auth/forgot-password/", {"email": self.user.email}, format="json")
        r = self.client.post("/api/auth/reset-password/",
                             {"email": self.user.email, "otp": "000000", "new_password": NEW_PASSWORD},
                             format="json")
        self.assertEqual(r.status_code, 400)

    def test_reset_rejects_weak_password(self):
        self.client.post("/api/auth/forgot-password/", {"email": self.user.email}, format="json")
        code = last_otp_from_mail()
        r = self.client.post("/api/auth/reset-password/",
                             {"email": self.user.email, "otp": code, "new_password": "1234"},
                             format="json")
        self.assertEqual(r.status_code, 400)