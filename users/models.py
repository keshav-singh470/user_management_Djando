from django.contrib.auth.models import AbstractUser
from django.db import models

class Profile(models.Model):
    name = models.CharField(max_length=50, unique=True) # e.g. Admin, Developer, HR, Manager
    description = models.TextField(blank=True, null=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name


class User(AbstractUser):
    email = models.EmailField(unique=True)
    profiles = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    
    STATUS_CHOICES = [('Active', 'Active'), ('Inactive', 'Inactive')]
    GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')]
    BLOOD_CHOICES = [(b, b) for b in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']]

    # first_name, last_name, username already available in AbstractUser 
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


# Projects
class Project(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('On Hold', 'On Hold'),
    ]

    title = models.CharField(max_length=200)
    type = models.CharField(max_length=100) # e.g. Web App, Mobile App, AI, etc.
    date_of_completion = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    description = models.TextField(null=True, blank=True)

    # Relations (Client and Manager)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name='projects' )
    assigned_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_projects')

    # Soft Delete tracking
    is_active = models.BooleanField(default=True) # False it means soft deleted
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='deleted_projects')

    # Audit Tracking (Kisne banaya / kab update hua)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_projects')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_projects')

    class Meta:
        ordering = ['-id']

    def __str__(self):
        # 2. Safe if client is None 
        client_name = self.client.first_name if self.client else "No Client"
        return f"{self.title} ({client_name})"

 

class ProjectAttachment(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='attachments'
    )
    file = models.FileField(upload_to='project_attachments/')
    file_name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_attachments'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file_name} ({self.project.title})"
