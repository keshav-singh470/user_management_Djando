from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


# ==========================================
# BASE CLASS (abstract = no table of its own)
# ==========================================

class AuditModel(models.Model):
    """
    Common tracking fields for models that support soft delete:
    who created, who modified, who deleted, and when.
    Restore fields are NOT here. A model that supports restore defines them itself.
    Hard delete is NOT inherited. Models that need it define it in their own class.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='%(class)s_created')

    modified_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='%(class)s_modified')

    is_active = models.BooleanField(default=True)   # False = soft deleted
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='%(class)s_deleted')

    class Meta:
        abstract = True


# ==========================================
# MODELS
# ==========================================

class Profile(models.Model):
    """Hard delete only, so it does not inherit AuditModel."""
    name = models.CharField(max_length=50, unique=True, null=True, blank=True)  # e.g. Admin, Developer, HR, Manager
    is_default = models.BooleanField(default=False)   # True = system profile, cannot be updated or deleted

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='profile_created')
    modified_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='profile_modified')

    def __str__(self):
        return self.name or ""

class LookupValue(models.Model):
    """
    Admin-managed values for dropdowns: project type, project status, task status.
    Hard delete only, so it does not inherit AuditModel.
    """
    CATEGORY_CHOICES = [
        ('project_type', 'Project Type'),
        ('project_status', 'Project Status'),
        ('task_status', 'Task Status'),
    ]

    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    name = models.CharField(max_length=100) 
    is_default = models.BooleanField(default=False)   # True = system value, cannot be updated or deleted

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='lookupvalue_created')
    modified_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='lookupvalue_modified')

    class Meta:
        ordering = ['category', 'name']
        constraints = [
            models.UniqueConstraint(Lower('name'), 'category', name='unique_lookup_name_per_category'),
        ]

    def __str__(self):
        return self.name

# AbstractUser must come first so that its own is_active field is used
class User(AbstractUser, AuditModel):
    # email: "required" and "unique" are enforced in the serializer, not in the model
    profiles = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')

    STATUS_CHOICES = [('Active', 'Active'), ('Inactive', 'Inactive')]
    GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')]
    BLOOD_CHOICES = [(b, b) for b in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']]

    # first_name, last_name, username are already available in AbstractUser
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    nationality = models.CharField(max_length=50, blank=True, null=True)
    image = models.ImageField(upload_to='users/', null=True, blank=True)
    blood_group = models.CharField(max_length=3, choices=BLOOD_CHOICES, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    permanent_address = models.TextField(blank=True, null=True)
    current_address = models.TextField(blank=True, null=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_number = models.CharField(max_length=15, blank=True, null=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active')
    company_name = models.CharField(max_length=150, blank=True, null=True)   # required only for the Client profile

    # Restore tracking (defined here because User supports restore)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='restored_users')

    def __str__(self):
        return self.email


class Client(AuditModel):
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    countries = models.CharField(max_length=100, null=True, blank=True)
    contact_no = models.CharField(max_length=20, null=True, blank=True)
    email_id = models.EmailField(unique=True, null=True, blank=True)

    # Restore tracking (defined here because Client supports restore)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='restored_clients')

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email_id})"


class Project(AuditModel):
   
    title = models.CharField(max_length=200, null=True, blank=True)
    type = models.ForeignKey(LookupValue, on_delete=models.PROTECT, null=True, blank=True,
                             related_name='projects_by_type', limit_choices_to={'category': 'project_type'})   # e.g. Web App, Mobile App, AI
    date_of_completion = models.DateField(null=True, blank=True)
    status = models.ForeignKey(LookupValue, on_delete=models.PROTECT, null=True, blank=True,
                               related_name='projects_by_status', limit_choices_to={'category': 'project_status'})
    description = models.TextField(null=True, blank=True)

    # Relations (client and manager)
    client = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='client_projects', limit_choices_to={'profiles__name': 'Client'})
    assigned_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_projects')
    # Team Leaders assigned by the Manager (a project may have many, a Team Leader may be on many projects)
    team_leaders = models.ManyToManyField(User, blank=True, related_name='led_projects',
                                          limit_choices_to={'profiles__name': 'Team Leader'})

    # Restore tracking (defined here because Project supports restore)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='restored_projects')

    class Meta:
        ordering = ['-id']

    def __str__(self):
        client_name = self.client.first_name if self.client else "No Client"
        return f"{self.title} ({client_name})"


class ProjectAttachment(models.Model):
    """Part of a project, uploaded together with it. Hard delete only, so it does not inherit AuditModel."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='project_attachments/')
    file_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file_name} ({self.project.title})"


class ProjectTask(AuditModel):
    # No restore fields for now (not required yet). Add them here if restore is needed later.
    PRIORITY_CHOICES = [('Low', 'Low'), ('Medium', 'Medium'), ('High', 'High')]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')

    title = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    status = models.ForeignKey(LookupValue, on_delete=models.PROTECT, null=True, blank=True,
                               related_name='tasks_by_status', limit_choices_to={'category': 'task_status'})
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')

    start_date = models.DateField(null=True, blank=True)
    deadline_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)   # actual completion date
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.title} ({self.project.title})"


class TaskComment(AuditModel):
    # No restore fields for now (not required yet).
    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_comments')
    comment = models.TextField(null=True, blank=True)
    hours_spent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Comment on {self.task.title}"

class TaskAttachment(models.Model):
    """A file attached to a task. Hard delete only, like ProjectAttachment."""
    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='task_attachments/')
    file_name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='task_attachments')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file_name} ({self.task.title})"


class ActivityLog(models.Model):
    """Who did what and when. Rows are only added, never edited or deleted through the API."""
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='activities')
    task = models.ForeignKey(ProjectTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activities')
    action = models.CharField(max_length=20)            # created, updated, deleted, restored, assigned, commented, attached
    description = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.description