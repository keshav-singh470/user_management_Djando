from rest_framework.permissions import BasePermission, SAFE_METHODS


def role_of(user):
    return user.profiles.name if getattr(user, 'profiles', None) else None


CLIENT_ROLE = 'Client'
CLIENT_BLOCKED_MESSAGE = "Client accounts cannot use this resource."


class IsNotClient(BasePermission):
    """Client ko is URL se door rakhta hai (jaise internal comments)."""
    message = CLIENT_BLOCKED_MESSAGE

    def has_permission(self, request, view):
        return role_of(request.user) != CLIENT_ROLE


class RoleWritePermission(BasePermission):
    """Read (GET): any logged-in user. Client sirf wahan jahan client_can_read=True. Write: sirf write_roles."""
    write_roles = ()
    client_can_read = False

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        role = role_of(user)
        if role == CLIENT_ROLE:
            if request.method in SAFE_METHODS and self.client_can_read:
                return True
            self.message = ('Client accounts have read-only access to their own projects and tasks.'
                            if self.client_can_read else CLIENT_BLOCKED_MESSAGE)
            return False
        if request.method in SAFE_METHODS:
            return True
        if role in self.write_roles:
            return True
        self.message = (f"Your role ({role or 'no role assigned'}) cannot {request.method} this resource. "
                        f"Allowed roles: {', '.join(self.write_roles)}.")
        return False


class UserWritePermission(RoleWritePermission):
    write_roles = ('Super Admin', 'Admin', 'Human Resource')

class ProfileWritePermission(RoleWritePermission):
    write_roles = ('Super Admin', 'Admin')

class ClientWritePermission(RoleWritePermission):      # OLD: Client table ke liye, Sir ke kehne par hatana hai
    write_roles = ('Super Admin', 'Admin', 'Manager')

class ProjectWritePermission(RoleWritePermission):
    write_roles = ('Super Admin', 'Admin', 'Manager')
    client_can_read = True          # Client apne projects padh sakta hai (scoping views mein hai)