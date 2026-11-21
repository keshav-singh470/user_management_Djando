from django.db.models import Q

from .models import Project, ProjectTask
from .permissions import role_of

FULL_ACCESS_ROLES = ('Super Admin', 'Admin')


def visible_projects(user):
    """Wo projects jo is user ko dikhne chahiye. Har list/detail isi se shuru hoti hai."""
    role = role_of(user)
    if role in FULL_ACCESS_ROLES:
        return Project.objects.all()
    if role == 'Manager':
        return Project.objects.filter(Q(assigned_manager=user) | Q(created_by=user))
    if role == 'Client':
        return Project.objects.filter(client=user)
    if role == 'Team Leader':
        return Project.objects.filter(
            Q(tasks__assigned_to=user) | Q(tasks__created_by=user), tasks__is_active=True).distinct()
    if role == 'Developer':
        return Project.objects.filter(tasks__assigned_to=user, tasks__is_active=True).distinct()
    return Project.objects.none()          # baaki sab roles ko kuch nahi


def visible_tasks(user):
    """Wo tasks jo is user ko dikhne chahiye."""
    role = role_of(user)
    if role in FULL_ACCESS_ROLES:
        return ProjectTask.objects.all()
    if role in ('Manager', 'Team Leader', 'Client'):
        return ProjectTask.objects.filter(project__in=visible_projects(user))
    if role == 'Developer':
        return ProjectTask.objects.filter(assigned_to=user)
    return ProjectTask.objects.none()


def can_see_inactive(user):
    """Soft-deleted records (?all=true / ?is_active=false) sirf in roles ko."""
    return role_of(user) in ('Super Admin', 'Admin', 'Manager')