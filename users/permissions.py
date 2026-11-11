from rest_framework.permissions import BasePermission, SAFE_METHODS


def role_of(user):
    return user.profiles.name if getattr(user, 'profiles', None) else None


class RoleWritePermission(BasePermission):
    """Read (GET): any logged-in user. Write (POST/PUT/PATCH/DELETE): only write_roles."""
    write_roles = ()

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_superuser or role_of(user) in self.write_roles


class UserWritePermission(RoleWritePermission):
    write_roles = ('Super Admin', 'Admin', 'Human Resource')

class ProfileWritePermission(RoleWritePermission):
    write_roles = ('Super Admin', 'Admin')

class ClientWritePermission(RoleWritePermission):
    write_roles = ('Super Admin', 'Admin', 'Manager')

class ProjectWritePermission(RoleWritePermission):
    write_roles = ('Super Admin', 'Admin', 'Manager')