from django.contrib.auth.models import AbstractUser
from django.db import models


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

    # first_name, last_name, username already available in AbstractUser 
    email = models.EmailField(unique=True)
    profiles = models.CharField(max_length=20, choices=PROFILE_CHOICES, default='Standard')
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    nationality = models.CharField(max_length=50, blank=True, null=True)
    image = models.ImageField(upload_to='users/', null=True, blank=True)
    blood_group = models.CharField(max_length=3, choices=BLOOD_CHOICES, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    permanent_address = models.TextField(blank=True, null=True)
    current_address = models.TextField(blank=True, null = True)
    emergency_contact_name = models.CharField(max_length=100, blank=True, null = True)
    emergency_contact_number = models.CharField(max_length=15, blank=True, null = True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True, null = True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active')

    def __str__(self):
        return self.email


# clients

class Client(models.Model):
    
    first_name = models.CharField(max_length=100, null = True, blank = True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    countries = models.CharField(max_length=100, null=True, blank=True)
    contact_no = models.CharField(max_length=20, null=True, blank=True)
    email_id = models.EmailField(unique=True, null = True, blank = True)
    is_active = models.BooleanField(default=True)
    
    # Timestamps (when was it created?)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)   

    # Audit tracking (who did it)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_clients')   
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_clients')   
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='deleted_clients')   

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email_id})"
