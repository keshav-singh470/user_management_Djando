from django.db.models import Q

from .models import Project, ProjectTask
from .permissions import role_of

FULL_ACCESS_ROLES = ('Super Admin', 'Admin')


def visible_projects(user):
    """Projects this user may see. Every list and detail view starts from this."""
    role = role_of(user)
    if role in FULL_ACCESS_ROLES:
        return Project.objects.all()
    if role == 'Manager':
        return Project.objects.filter(assigned_manager=user)          # only an Admin creates projects
    if role == 'Client':
        return Project.objects.filter(client=user)
    if role == 'Team Leader':
        return Project.objects.filter(team_leaders=user)              # projects the Manager assigned to him
    if role == 'Developer':
        return Project.objects.filter(tasks__assigned_to=user, tasks__is_active=True).distinct()
    return Project.objects.none()


def visible_tasks(user):
    """Tasks this user may see."""
    role = role_of(user)
    if role in FULL_ACCESS_ROLES:
        return ProjectTask.objects.all()
    if role in ('Manager', 'Client'):
        return ProjectTask.objects.filter(project__in=visible_projects(user))
    if role == 'Team Leader':
        # only his own team's work: tasks he created (or old tasks assigned to him)
        return ProjectTask.objects.filter(project__in=visible_projects(user)).filter(
            Q(created_by=user) | Q(assigned_to=user))
    if role == 'Developer':
        return ProjectTask.objects.filter(assigned_to=user)
    return ProjectTask.objects.none()


def can_see_inactive(user):
    """Soft-deleted records (?all=true / ?is_active=false) only for these roles."""
    return role_of(user) in ('Super Admin', 'Admin', 'Manager')