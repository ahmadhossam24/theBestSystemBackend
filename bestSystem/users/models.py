from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
# Create your models here.

# Choices for user roles
class UserRole(models.TextChoices):
    COMPANY_BOSS = 'company_boss', 'Company Boss'
    BRANCH_ADMIN = 'branch_admin', 'Branch Admin'
    TEAM_ADMIN = 'team_admin', 'Team Admin'
    TEAM_AGENT = 'team_agent', 'Team Agent'

# boss_manager user will be created by (from cmd)
# python manage.py makemigrations users
# python manage.py migrate
# python manage.py createsuperuser
# This user will have role=company_boss and creator=None (since no one created it). All other users will need a creator when created via the API.

# Choices for agent sub‑roles (to be extended later)
class AgentRole(models.TextChoices):
    # Add your agent types here later
    DEFAULT = 'default', 'Default Agent'

class User(AbstractUser):
    """
    Custom user model that includes all fields required for the hierarchy.
    The role field determines the user type.
    """
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.TEAM_AGENT,
    )
    name = models.CharField(max_length=255)  # full name
    user_information = models.TextField(blank=True, null=True)

    # Relationships
    branch = models.ForeignKey(
        'Branch',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
    )
    team = models.ForeignKey(
        'Team',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
    )
    agent_role = models.CharField(
        max_length=20,
        choices=AgentRole.choices,
        blank=True,
        null=True,
        help_text="Only used when role = team_agent",
    )

    # Audit fields (nullable for company_boss)
    date_created = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_users',
    )
    is_deleted = models.BooleanField(default=False)
    deleter = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deleted_users',
    )
    date_deleted = models.DateTimeField(null=True, blank=True)

    # Edits will be logged via the generic EditLog model (see below)
    edits = GenericRelation('EditLog')

    groups = models.ManyToManyField(
        'auth.Group',
        blank=True,
        related_name='custom_user_set',
        related_query_name='user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        blank=True,
        related_name='custom_user_set',
        related_query_name='user',
    )

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['branch']),
            models.Index(fields=['team']),
        ]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Branch(models.Model):
    name = models.CharField(max_length=255, unique=True)
    location = models.CharField(max_length=255, blank=True)
    information = models.TextField(blank=True)

    # Audit fields
    date_created = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_branches',
    )
    is_deleted = models.BooleanField(default=False)
    deleter = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deleted_branches',
    )
    date_deleted = models.DateTimeField(null=True, blank=True)

    # Edits log
    edits = GenericRelation('EditLog')

    class Meta:
        db_table = 'branches'
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


class BranchPhone(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='phones',
    )
    phone_number = models.CharField(max_length=20)

    class Meta:
        db_table = 'branch_phones'
        unique_together = [['branch', 'phone_number']]  # prevent duplicate numbers per branch

    def __str__(self):
        return f"{self.branch.name}: {self.phone_number}"


class Team(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name='teams',
    )
    name = models.CharField(max_length=255)
    information = models.TextField(blank=True)

    # Audit fields
    date_created = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_teams',
    )
    is_deleted = models.BooleanField(default=False)
    deleter = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deleted_teams',
    )
    date_deleted = models.DateTimeField(null=True, blank=True)

    # Edits log
    edits = GenericRelation('EditLog')

    class Meta:
        db_table = 'teams'
        unique_together = [['branch', 'name']]  # team name unique within a branch
        indexes = [
            models.Index(fields=['branch']),
        ]

    def __str__(self):
        return f"{self.branch.name} - {self.name}"


class UserPhone(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='phones',
    )
    phone_number = models.CharField(max_length=20)

    class Meta:
        db_table = 'user_phones'
        unique_together = [['user', 'phone_number']]

    def __str__(self):
        return f"{self.user.username}: {self.phone_number}"


class EditLog(models.Model):
    """
    Generic log for edits on User, Branch, and Team.
    The `editor` is the user who performed the edit.
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    edit_date = models.DateTimeField(auto_now_add=True)
    editor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='edits_made')
    description = models.TextField(blank=True, help_text="Description of the change")

    class Meta:
        db_table = 'edit_logs'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['edit_date']),
        ]

    def __str__(self):
        return f"Edit by {self.editor.username} on {self.edit_date}"

