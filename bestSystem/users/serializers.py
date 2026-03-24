from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from .models import (
    User, Branch, Team, UserPhone, BranchPhone, EditLog,
    UserRole, AgentRole
)

class UserPhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPhone
        fields = ['id', 'phone_number']
        extra_kwargs = {
            'phone_number': {'required': True}
        }


class BranchPhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = BranchPhone
        fields = ['id', 'phone_number']
        extra_kwargs = {
            'phone_number': {'required': True}
        }


class BranchSerializer(serializers.ModelSerializer):
    phones = BranchPhoneSerializer(many=True, read_only=False, required=False)
    # Include edit logs if needed
    # edits = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'location', 'information',
            'phones',
            'date_created', 'creator',
            'is_deleted', 'deleter', 'date_deleted',
            # 'edits'
        ]
        read_only_fields = ['id', 'date_created', 'creator', 'is_deleted', 'deleter', 'date_deleted']

    def create(self, validated_data):
        phones_data = validated_data.pop('phones', [])
        # Set creator from context (current user)
        validated_data['creator'] = self.context['request'].user
        branch = Branch.objects.create(**validated_data)
        for phone_data in phones_data:
            BranchPhone.objects.create(branch=branch, **phone_data)
        return branch

    def update(self, instance, validated_data):
        phones_data = validated_data.pop('phones', None)
        # Update branch fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        # Update phones if provided (replace all)
        if phones_data is not None:
            instance.phones.all().delete()
            for phone_data in phones_data:
                BranchPhone.objects.create(branch=instance, **phone_data)
        return instance


class TeamSerializer(serializers.ModelSerializer):
    # Read-only nested branch info (optional)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = Team
        fields = [
            'id', 'branch', 'branch_name', 'name', 'information',
            'date_created', 'creator',
            'is_deleted', 'deleter', 'date_deleted',
        ]
        read_only_fields = ['id', 'date_created', 'creator', 'is_deleted', 'deleter', 'date_deleted']

    def validate(self, attrs):
        # Ensure branch exists and is not deleted (we can add a check)
        branch = attrs.get('branch')
        if branch and branch.is_deleted:
            raise serializers.ValidationError({"branch": "Cannot create team for a deleted branch."})
        return attrs

    def create(self, validated_data):
        validated_data['creator'] = self.context['request'].user
        return Team.objects.create(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    phones = UserPhoneSerializer(many=True, read_only=False, required=False)
    # Include role choices as string representation
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    agent_role_display = serializers.CharField(source='get_agent_role_display', read_only=True)

    # Read-only fields to show related names
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)
    creator_username = serializers.CharField(source='creator.username', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'password', 'name', 'role', 'role_display',
            'user_information', 'branch', 'branch_name', 'team', 'team_name',
            'agent_role', 'agent_role_display',
            'phones',
            'date_created', 'creator', 'creator_username',
            'is_deleted', 'deleter', 'date_deleted',
        ]
        read_only_fields = [
            'id', 'date_created', 'creator', 'is_deleted', 'deleter', 'date_deleted',
            'branch_name', 'team_name', 'creator_username', 'role_display', 'agent_role_display'
        ]
        extra_kwargs = {
            'password': {'write_only': False, 'required': False},
            'email': {'required': False, 'allow_blank': True},
            'username': {'required': True},
            'name': {'required': True},
            'role': {'required': True},
            'branch': {'required': False, 'allow_null': True},
            'team': {'required': False, 'allow_null': True},
            'agent_role': {'required': False, 'allow_null': True},
        }

    def validate(self, attrs):
        role = attrs.get('role')
        branch = attrs.get('branch')
        team = attrs.get('team')
        agent_role = attrs.get('agent_role')

        # Role-based validations
        if role == UserRole.COMPANY_BOSS:
            if branch is not None or team is not None:
                raise serializers.ValidationError("Company boss cannot have branch or team assigned.")
        elif role == UserRole.BRANCH_ADMIN:
            if branch is None:
                raise serializers.ValidationError("Branch admin must be assigned to a branch.")
            if team is not None:
                raise serializers.ValidationError("Branch admin cannot have a team assigned.")
        elif role in [UserRole.TEAM_ADMIN, UserRole.TEAM_AGENT]:
            if team is None:
                raise serializers.ValidationError(f"{role} must be assigned to a team.")
            # Validate that branch is consistent with team (if branch provided)
            if branch is not None and branch != team.branch:
                raise serializers.ValidationError("Team's branch does not match provided branch.")
            # If no branch provided, set it from team
            if branch is None and team is not None:
                attrs['branch'] = team.branch
            if role == UserRole.TEAM_AGENT and agent_role is None:
                raise serializers.ValidationError("Team agent must have an agent_role specified.")
        else:
            # Unknown role – shouldn't happen because choices
            pass

        # Creator validation (for creation only)
        request = self.context.get('request')
        if request and request.method == 'POST':
            creator = request.user
            # Ensure creator is allowed to create this user type
            # We'll handle permissions in views, but also can add basic checks here
            if creator.role == UserRole.COMPANY_BOSS:
                # can create any
                pass
            elif creator.role == UserRole.BRANCH_ADMIN:
                # can create team_admin, team_agent only under their branch
                if role not in [UserRole.TEAM_ADMIN, UserRole.TEAM_AGENT]:
                    raise serializers.ValidationError("Branch admin can only create team admins and team agents.")
                # Ensure branch is the creator's branch
                if branch and branch != creator.branch:
                    raise serializers.ValidationError("Branch admin can only create users in their own branch.")
            elif creator.role == UserRole.TEAM_ADMIN:
                # can create team_agent only under their team
                if role != UserRole.TEAM_AGENT:
                    raise serializers.ValidationError("Team admin can only create team agents.")
                # Ensure team is the creator's team
                if team and team != creator.team:
                    raise serializers.ValidationError("Team admin can only create users in their own team.")
            else:
                # team_agent and others cannot create users
                raise serializers.ValidationError("You do not have permission to create users.")

        return attrs

    def create(self, validated_data):
        phones_data = validated_data.pop('phones', [])
        password = validated_data.pop('password', None)
        # Set creator from context (current user)
        validated_data['creator'] = self.context['request'].user

        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            # Generate a random password? Or set a placeholder; we'll enforce in view
            user.set_unusable_password()
        user.save()

        for phone_data in phones_data:
            UserPhone.objects.create(user=user, **phone_data)
        return user

    def update(self, instance, validated_data):
        # For updates, we don't allow changing creator, date_created, etc.
        phones_data = validated_data.pop('phones', None)
        password = validated_data.pop('password', None)

        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()

        # Update phones (replace all)
        if phones_data is not None:
            instance.phones.all().delete()
            for phone_data in phones_data:
                UserPhone.objects.create(user=instance, **phone_data)
        return instance


class EditLogSerializer(serializers.ModelSerializer):
    # Show editor's username
    editor_username = serializers.CharField(source='editor.username', read_only=True)
    # For generic foreign key, we might want to show the object type and id
    content_type_name = serializers.CharField(source='content_type.model', read_only=True)

    class Meta:
        model = EditLog
        fields = [
            'id', 'content_type', 'object_id', 'content_type_name',
            'edit_date', 'editor', 'editor_username', 'description'
        ]
        read_only_fields = ['id', 'edit_date', 'editor']