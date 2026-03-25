from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions
from django.db.models import Q
from .models import User, Branch, Team, EditLog, UserRole
from .serializers import (
    UserSerializer, BranchSerializer, TeamSerializer, EditLogSerializer
)
from .permissions import IsCompanyBoss, IsBranchAdmin, IsTeamAdmin, IsOwnerOrCreator, IsCreatorOrAdmin
from datetime import timezone

class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for User model.
    GET /users/ - list (filtered by role)
    POST /users/ - create (only allowed by appropriate role)
    GET /users/{id}/ - retrieve
    PUT/PATCH /users/{id}/ - update
    DELETE /users/{id}/ - soft delete (set is_deleted=True)
    """
    queryset = User.objects.filter(is_deleted=False).select_related('branch', 'team', 'creator')
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'branch', 'team', 'is_deleted']
    search_fields = ['username', 'name', 'email']
    ordering_fields = ['date_created', 'username']

    def get_permissions(self):
        # Assign permissions based on action
        if self.action == 'create':
            # Allow any authenticated user to create, but serializers will validate permissions
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated, IsCreatorOrAdmin, IsOwnerOrCreator]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        # Apply role-based filtering
        if user.role == UserRole.COMPANY_BOSS:
            # company boss sees all non-deleted users
            return super().get_queryset()
        elif user.role == UserRole.BRANCH_ADMIN:
            # branch admin sees users in their branch (excluding company boss)
            return super().get_queryset().filter(branch=user.branch)
        elif user.role == UserRole.TEAM_ADMIN:
            # team admin sees users in their team
            return super().get_queryset().filter(team=user.team)
        elif user.role == UserRole.TEAM_AGENT:
            # team agent only sees themselves
            return super().get_queryset().filter(id=user.id)
        else:
            return User.objects.none()

    def perform_create(self, serializer):
        # The creator is set in serializer's create method using request.user
        serializer.save()

    def perform_destroy(self, instance):
        # Soft delete: set is_deleted=True and record deleter
        instance.is_deleted = True
        instance.deleter = self.request.user
        instance.date_deleted = timezone.now()
        instance.save()

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        """Return current user's profile."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class BranchViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Branch model.
    """
    queryset = Branch.objects.filter(is_deleted=False)
    serializer_class = BranchSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'location']
    ordering_fields = ['date_created', 'name']

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [permissions.IsAuthenticated, IsCompanyBoss]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated, IsCreatorOrAdmin, IsOwnerOrCreator]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.COMPANY_BOSS:
            return super().get_queryset()
        elif user.role == UserRole.BRANCH_ADMIN:
            # branch admin only sees their own branch
            return super().get_queryset().filter(id=user.branch.id) if user.branch else Branch.objects.none()
        else:
            # others see nothing or maybe all (but we restrict via permissions)
            return Branch.objects.none()

    def perform_destroy(self, instance):
        # Soft delete
        instance.is_deleted = True
        instance.deleter = self.request.user
        instance.date_deleted = timezone.now()
        instance.save()


class TeamViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Team model.
    """
    queryset = Team.objects.filter(is_deleted=False).select_related('branch')
    serializer_class = TeamSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'branch__name']
    ordering_fields = ['date_created', 'name']

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated, IsCreatorOrAdmin, IsOwnerOrCreator]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.COMPANY_BOSS:
            return super().get_queryset()
        elif user.role == UserRole.BRANCH_ADMIN:
            # branch admin sees teams under their branch
            return super().get_queryset().filter(branch=user.branch)
        elif user.role == UserRole.TEAM_ADMIN:
            # team admin sees their own team
            return super().get_queryset().filter(id=user.team.id) if user.team else Team.objects.none()
        else:
            return Team.objects.none()

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleter = self.request.user
        instance.date_deleted = timezone.now()
        instance.save()


class EditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view for edit logs. Users can see logs for objects they have access to.
    """
    serializer_class = EditLogSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['edit_date']
    ordering = ['-edit_date']

    def get_queryset(self):
        user = self.request.user
        # Restrict logs to objects the user can view
        # For simplicity, we'll show logs for users, branches, teams accessible to the user
        # This can be complex; we'll implement a basic version: 
        # - company boss sees all logs
        # - branch admin sees logs for their branch and teams under it, and users under those
        # - team admin sees logs for their team and users under it
        # - team agent sees only their own logs

        if user.role == UserRole.COMPANY_BOSS:
            return EditLog.objects.all()
        elif user.role == UserRole.BRANCH_ADMIN and user.branch:
            # Logs for this branch, its teams, and users in those
            branch = user.branch
            branch_logs = Q(content_type__model='branch', object_id=branch.id)
            team_logs = Q(content_type__model='team', object_id__in=branch.teams.values_list('id', flat=True))
            user_logs = Q(content_type__model='user', object_id__in=User.objects.filter(branch=branch).values_list('id', flat=True))
            return EditLog.objects.filter(branch_logs | team_logs | user_logs)
        elif user.role == UserRole.TEAM_ADMIN and user.team:
            team = user.team
            team_logs = Q(content_type__model='team', object_id=team.id)
            user_logs = Q(content_type__model='user', object_id__in=User.objects.filter(team=team).values_list('id', flat=True))
            return EditLog.objects.filter(team_logs | user_logs)
        elif user.role == UserRole.TEAM_AGENT:
            return EditLog.objects.filter(content_type__model='user', object_id=user.id)
        else:
            return EditLog.objects.none()