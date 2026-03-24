from rest_framework import permissions
from .models import UserRole,User,Team,Branch

class IsCompanyBoss(permissions.BasePermission):
    """Allows access only to users with role=company_boss."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.COMPANY_BOSS

class IsBranchAdmin(permissions.BasePermission):
    """Allows access only to users with role=branch_admin."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.BRANCH_ADMIN

class IsTeamAdmin(permissions.BasePermission):
    """Allows access only to users with role=team_admin."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.TEAM_ADMIN

class IsTeamAgent(permissions.BasePermission):
    """Allows access only to users with role=team_agent."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.TEAM_AGENT

class IsOwnerOrCreator(permissions.BasePermission):
    """
    Custom permission to allow:
    - company_boss: any operation (full access)
    - branch_admin: on users/branches/teams within their branch
    - team_admin: on users/teams within their team
    - team_agent: only on their own user object (read/update)
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        # Company boss can do anything
        if user.role == UserRole.COMPANY_BOSS:
            return True

        # Determine object type and apply hierarchy rules
        if isinstance(obj, User):
            # Users can view/edit themselves
            if obj == user:
                return True
            # Branch admin can manage users in their branch
            if user.role == UserRole.BRANCH_ADMIN:
                return obj.branch == user.branch
            # Team admin can manage users in their team
            if user.role == UserRole.TEAM_ADMIN:
                return obj.team == user.team
            return False

        elif isinstance(obj, Branch):
            # Branch admin can manage their own branch
            if user.role == UserRole.BRANCH_ADMIN:
                return obj == user.branch
            # Team admin cannot manage branches
            return False

        elif isinstance(obj, Team):
            # Branch admin can manage teams under their branch
            if user.role == UserRole.BRANCH_ADMIN:
                return obj.branch == user.branch
            # Team admin can manage their own team
            if user.role == UserRole.TEAM_ADMIN:
                return obj == user.team
            return False

        return False

class IsCreatorOrAdmin(permissions.BasePermission):
    """
    For actions that modify resources (create/update/delete), we check if the user
    has permission based on their role and the object's creator chain.
    This can be combined with IsOwnerOrCreator for object-level checks.
    """
    def has_permission(self, request, view):
        # For list or create actions, we rely on the view's queryset filtering
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role == UserRole.COMPANY_BOSS:
            return True
        # For non-company-boss, we use the hierarchy checks in IsOwnerOrCreator
        # So we delegate there.
        return IsOwnerOrCreator().has_object_permission(request, view, obj)