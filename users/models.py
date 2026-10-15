from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    PROFILE_CHOICES = [
        ('Administrator', 'Administrator'),
        ('Standard', 'Standard'),
        ('Developer', 'Developer'),
        ('Client', 'Client'),
        ('Human Resource', 'Human Resource'),
    ]
    STATUS_CHOICES = [('Active', 'Active'), ('Inactive', 'Inactive')]
    GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')]
    BLOOD_CHOICES = [(b, b) for b in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']]

    # first_name, last_name, username AbstractUser me pehle se hain
    email = models.EmailField(unique=True)
    profiles = models.CharField(max_length=20, choices=PROFILE_CHOICES, default='Standard')
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    nationality = models.CharField(max_length=50, blank=True)
    image = models.ImageField(upload_to='users/', null=True, blank=True)
    blood_group = models.CharField(max_length=3, choices=BLOOD_CHOICES, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    permanent_address = models.TextField(blank=True)
    current_address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_number = models.CharField(max_length=15, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active')

    def __str__(self):
        return self.email


class OTP(models.Model):
    PURPOSE_CHOICES = [('verify', 'Verify'), ('reset', 'Reset Password')]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=128)   # OTP hash karke store hota hai
    purpose = models.CharField(max_length=10, choices=PURPOSE_CHOICES)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)