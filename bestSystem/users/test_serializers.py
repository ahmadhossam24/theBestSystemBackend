from django.test import TestCase, RequestFactory
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from unittest.mock import MagicMock

from .models import User, Branch, Team, UserPhone, BranchPhone, EditLog, UserRole, AgentRole
from .serializers import (
    UserSerializer, UserPhoneSerializer,
    BranchSerializer, BranchPhoneSerializer,
    TeamSerializer, EditLogSerializer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_boss(**kwargs):
    defaults = dict(username="boss", name="Boss User", role=UserRole.COMPANY_BOSS)
    defaults.update(kwargs)
    return User.objects.create_user(password="pass", **defaults)


def make_branch(creator, **kwargs):
    defaults = dict(name="Main Branch", creator=creator)
    defaults.update(kwargs)
    return Branch.objects.create(**defaults)


def make_team(branch, creator, **kwargs):
    defaults = dict(branch=branch, name="Alpha Team", creator=creator)
    defaults.update(kwargs)
    return Team.objects.create(**defaults)


def make_user(role, creator, branch=None, team=None, **kwargs):
    defaults = dict(
        username=f"user_{role}_{User.objects.count()}",
        name="Test User",
        role=role,
        creator=creator,
        branch=branch,
        team=team,
    )
    defaults.update(kwargs)
    return User.objects.create_user(password="pass", **defaults)


def fake_request(user, method="POST"):
    """Return a lightweight mock request with a user and method."""
    req = MagicMock()
    req.user = user
    req.method = method
    return req


# ===========================================================================
# UserPhoneSerializer
# ===========================================================================

class UserPhoneSerializerTest(TestCase):
    def test_valid_data(self):
        s = UserPhoneSerializer(data={"phone_number": "01012345678"})
        self.assertTrue(s.is_valid(), s.errors)

    def test_phone_number_required(self):
        s = UserPhoneSerializer(data={})
        self.assertFalse(s.is_valid())
        self.assertIn("phone_number", s.errors)

    def test_serializes_existing_instance(self):
        boss = make_boss()
        branch = make_branch(boss)
        agent = make_user(UserRole.TEAM_AGENT, boss, branch=branch)
        phone = UserPhone.objects.create(user=agent, phone_number="01099999999")
        s = UserPhoneSerializer(phone)
        self.assertEqual(s.data["phone_number"], "01099999999")
        self.assertEqual(s.data["id"], phone.id)


# ===========================================================================
# BranchPhoneSerializer
# ===========================================================================

class BranchPhoneSerializerTest(TestCase):
    def test_valid_data(self):
        s = BranchPhoneSerializer(data={"phone_number": "01012345678"})
        self.assertTrue(s.is_valid(), s.errors)

    def test_phone_number_required(self):
        s = BranchPhoneSerializer(data={})
        self.assertFalse(s.is_valid())
        self.assertIn("phone_number", s.errors)

    def test_serializes_existing_instance(self):
        boss = make_boss()
        branch = make_branch(boss)
        phone = BranchPhone.objects.create(branch=branch, phone_number="01011111111")
        s = BranchPhoneSerializer(phone)
        self.assertEqual(s.data["phone_number"], "01011111111")


# ===========================================================================
# BranchSerializer
# ===========================================================================

class BranchSerializerCreateTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.request = fake_request(self.boss)

    def test_create_branch_no_phones(self):
        data = {"name": "Downtown", "location": "City Center", "information": "Main branch"}
        s = BranchSerializer(data=data, context={"request": self.request})
        self.assertTrue(s.is_valid(), s.errors)
        branch = s.save()
        self.assertEqual(branch.name, "Downtown")
        self.assertEqual(branch.creator, self.boss)

    def test_create_branch_with_phones(self):
        data = {
            "name": "West Branch",
            "phones": [{"phone_number": "01011111111"}, {"phone_number": "01022222222"}],
        }
        s = BranchSerializer(data=data, context={"request": self.request})
        self.assertTrue(s.is_valid(), s.errors)
        branch = s.save()
        self.assertEqual(branch.phones.count(), 2)

    def test_name_is_required(self):
        s = BranchSerializer(data={}, context={"request": self.request})
        self.assertFalse(s.is_valid())
        self.assertIn("name", s.errors)

    def test_read_only_fields_ignored_on_input(self):
        data = {"name": "Branch X", "is_deleted": True, "creator": 999}
        s = BranchSerializer(data=data, context={"request": self.request})
        self.assertTrue(s.is_valid(), s.errors)
        branch = s.save()
        self.assertFalse(branch.is_deleted)
        self.assertEqual(branch.creator, self.boss)

    def test_serialized_output_contains_phones(self):
        branch = make_branch(self.boss, name="East")
        BranchPhone.objects.create(branch=branch, phone_number="01033333333")
        s = BranchSerializer(branch)
        phone_numbers = [p["phone_number"] for p in s.data["phones"]]
        self.assertIn("01033333333", phone_numbers)


class BranchSerializerUpdateTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss, name="Old Name")
        BranchPhone.objects.create(branch=self.branch, phone_number="01011111111")
        self.request = fake_request(self.boss, method="PATCH")

    def test_update_branch_name(self):
        s = BranchSerializer(
            self.branch, data={"name": "New Name"}, partial=True,
            context={"request": self.request}
        )
        self.assertTrue(s.is_valid(), s.errors)
        branch = s.save()
        self.assertEqual(branch.name, "New Name")

    def test_update_replaces_phones(self):
        s = BranchSerializer(
            self.branch,
            data={"name": self.branch.name, "phones": [{"phone_number": "01099999999"}]},
            context={"request": self.request}
        )
        self.assertTrue(s.is_valid(), s.errors)
        branch = s.save()
        phones = list(branch.phones.values_list("phone_number", flat=True))
        self.assertEqual(phones, ["01099999999"])

    def test_update_without_phones_keeps_existing(self):
        s = BranchSerializer(
            self.branch, data={"name": self.branch.name}, partial=True,
            context={"request": self.request}
        )
        self.assertTrue(s.is_valid(), s.errors)
        branch = s.save()
        self.assertEqual(branch.phones.count(), 1)


# ===========================================================================
# TeamSerializer
# ===========================================================================

class TeamSerializerCreateTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.request = fake_request(self.boss)

    def test_create_team(self):
        data = {"branch": self.branch.id, "name": "Support"}
        s = TeamSerializer(data=data, context={"request": self.request})
        self.assertTrue(s.is_valid(), s.errors)
        team = s.save()
        self.assertEqual(team.name, "Support")
        self.assertEqual(team.branch, self.branch)
        self.assertEqual(team.creator, self.boss)

    def test_branch_required(self):
        s = TeamSerializer(data={"name": "Support"}, context={"request": self.request})
        self.assertFalse(s.is_valid())
        self.assertIn("branch", s.errors)

    def test_cannot_create_team_for_deleted_branch(self):
        self.branch.is_deleted = True
        self.branch.save()
        data = {"branch": self.branch.id, "name": "Ghost Team"}
        s = TeamSerializer(data=data, context={"request": self.request})
        self.assertFalse(s.is_valid())
        self.assertIn("branch", s.errors)

    def test_branch_name_in_output(self):
        team = make_team(self.branch, self.boss, name="Sales")
        s = TeamSerializer(team)
        self.assertEqual(s.data["branch_name"], self.branch.name)

    def test_read_only_fields_ignored(self):
        data = {"branch": self.branch.id, "name": "Ops", "is_deleted": True, "creator": 999}
        s = TeamSerializer(data=data, context={"request": self.request})
        self.assertTrue(s.is_valid(), s.errors)
        team = s.save()
        self.assertFalse(team.is_deleted)
        self.assertEqual(team.creator, self.boss)


# ===========================================================================
# UserSerializer — validation
# ===========================================================================

class UserSerializerValidationTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.team = make_team(self.branch, self.boss)

    def _serialize(self, data, requester):
        return UserSerializer(data=data, context={"request": fake_request(requester)})

    # --- role: company_boss ---

    def test_boss_cannot_have_branch(self):
        s = self._serialize({
            "username": "newboss", "name": "New Boss",
            "role": UserRole.COMPANY_BOSS, "branch": self.branch.id,
        }, self.boss)
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)

    def test_boss_cannot_have_team(self):
        s = self._serialize({
            "username": "newboss", "name": "New Boss",
            "role": UserRole.COMPANY_BOSS, "team": self.team.id,
        }, self.boss)
        self.assertFalse(s.is_valid())

    # --- role: branch_admin ---

    def test_branch_admin_requires_branch(self):
        s = self._serialize({
            "username": "ba1", "name": "BA",
            "role": UserRole.BRANCH_ADMIN,
        }, self.boss)
        self.assertFalse(s.is_valid())

    def test_branch_admin_cannot_have_team(self):
        s = self._serialize({
            "username": "ba1", "name": "BA",
            "role": UserRole.BRANCH_ADMIN,
            "branch": self.branch.id, "team": self.team.id,
        }, self.boss)
        self.assertFalse(s.is_valid())

    def test_branch_admin_valid(self):
        s = self._serialize({
            "username": "ba1", "name": "BA",
            "role": UserRole.BRANCH_ADMIN, "branch": self.branch.id,
        }, self.boss)
        self.assertTrue(s.is_valid(), s.errors)

    # --- role: team_admin ---

    def test_team_admin_requires_team(self):
        s = self._serialize({
            "username": "ta1", "name": "TA",
            "role": UserRole.TEAM_ADMIN,
        }, self.boss)
        self.assertFalse(s.is_valid())

    def test_team_admin_branch_mismatch_raises(self):
        other_branch = make_branch(self.boss, name="Other Branch")
        s = self._serialize({
            "username": "ta1", "name": "TA",
            "role": UserRole.TEAM_ADMIN,
            "team": self.team.id, "branch": other_branch.id,
        }, self.boss)
        self.assertFalse(s.is_valid())

    def test_team_admin_auto_fills_branch_from_team(self):
        s = self._serialize({
            "username": "ta1", "name": "TA",
            "role": UserRole.TEAM_ADMIN, "team": self.team.id,
        }, self.boss)
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data["branch"], self.branch)

    # --- role: team_agent ---

    def test_team_agent_requires_agent_role(self):
        s = self._serialize({
            "username": "ag1", "name": "Agent",
            "role": UserRole.TEAM_AGENT, "team": self.team.id,
        }, self.boss)
        self.assertFalse(s.is_valid())

    def test_team_agent_valid(self):
        s = self._serialize({
            "username": "ag1", "name": "Agent",
            "role": UserRole.TEAM_AGENT, "team": self.team.id,
            "agent_role": AgentRole.DEFAULT,
        }, self.boss)
        self.assertTrue(s.is_valid(), s.errors)


# ===========================================================================
# UserSerializer — creator permission checks
# ===========================================================================

class UserSerializerCreatorPermissionsTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.branch2 = make_branch(self.boss, name="Branch 2")
        self.team = make_team(self.branch, self.boss)
        self.team2 = make_team(self.branch2, self.boss, name="Team 2")

        self.branch_admin = make_user(
            UserRole.BRANCH_ADMIN, self.boss, branch=self.branch, username="ba"
        )
        self.team_admin = make_user(
            UserRole.TEAM_ADMIN, self.boss, branch=self.branch, team=self.team, username="ta"
        )
        self.agent = make_user(
            UserRole.TEAM_AGENT, self.boss, branch=self.branch, team=self.team,
            username="ag", agent_role=AgentRole.DEFAULT
        )

    def _serialize(self, data, requester):
        return UserSerializer(data=data, context={"request": fake_request(requester)})

    def test_boss_can_create_branch_admin(self):
        s = self._serialize({
            "username": "ba2", "name": "BA2",
            "role": UserRole.BRANCH_ADMIN, "branch": self.branch.id,
        }, self.boss)
        self.assertTrue(s.is_valid(), s.errors)

    def test_branch_admin_can_create_team_agent(self):
        s = self._serialize({
            "username": "ag2", "name": "Ag2",
            "role": UserRole.TEAM_AGENT,
            "team": self.team.id, "agent_role": AgentRole.DEFAULT,
        }, self.branch_admin)
        self.assertTrue(s.is_valid(), s.errors)

    def test_branch_admin_cannot_create_branch_admin(self):
        s = self._serialize({
            "username": "ba3", "name": "BA3",
            "role": UserRole.BRANCH_ADMIN, "branch": self.branch.id,
        }, self.branch_admin)
        self.assertFalse(s.is_valid())

    def test_branch_admin_cannot_create_user_in_other_branch(self):
        team_in_other = make_team(self.branch2, self.boss, name="Foreign Team")
        s = self._serialize({
            "username": "ag3", "name": "Ag3",
            "role": UserRole.TEAM_AGENT,
            "team": team_in_other.id, "agent_role": AgentRole.DEFAULT,
        }, self.branch_admin)
        self.assertFalse(s.is_valid())

    def test_team_admin_can_create_agent_in_own_team(self):
        s = self._serialize({
            "username": "ag4", "name": "Ag4",
            "role": UserRole.TEAM_AGENT,
            "team": self.team.id, "agent_role": AgentRole.DEFAULT,
        }, self.team_admin)
        self.assertTrue(s.is_valid(), s.errors)

    def test_team_admin_cannot_create_team_admin(self):
        s = self._serialize({
            "username": "ta2", "name": "TA2",
            "role": UserRole.TEAM_ADMIN, "team": self.team.id,
        }, self.team_admin)
        self.assertFalse(s.is_valid())

    def test_team_admin_cannot_create_agent_in_other_team(self):
        s = self._serialize({
            "username": "ag5", "name": "Ag5",
            "role": UserRole.TEAM_AGENT,
            "team": self.team2.id, "agent_role": AgentRole.DEFAULT,
        }, self.team_admin)
        self.assertFalse(s.is_valid())

    def test_agent_cannot_create_user(self):
        s = self._serialize({
            "username": "ag6", "name": "Ag6",
            "role": UserRole.TEAM_AGENT,
            "team": self.team.id, "agent_role": AgentRole.DEFAULT,
        }, self.agent)
        self.assertFalse(s.is_valid())


# ===========================================================================
# UserSerializer — create / update
# ===========================================================================

class UserSerializerCreateUpdateTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.team = make_team(self.branch, self.boss)

    def test_create_sets_creator(self):
        s = UserSerializer(
            data={
                "username": "ag1", "name": "Agent",
                "role": UserRole.TEAM_AGENT, "team": self.team.id,
                "agent_role": AgentRole.DEFAULT, "password": "secret123",
            },
            context={"request": fake_request(self.boss)}
        )
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertEqual(user.creator, self.boss)

    def test_create_with_password_is_hashed(self):
        s = UserSerializer(
            data={
                "username": "ag2", "name": "Agent2",
                "role": UserRole.TEAM_AGENT, "team": self.team.id,
                "agent_role": AgentRole.DEFAULT, "password": "secret123",
            },
            context={"request": fake_request(self.boss)}
        )
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertTrue(user.check_password("secret123"))

    def test_create_without_password_sets_unusable(self):
        s = UserSerializer(
            data={
                "username": "ag3", "name": "Agent3",
                "role": UserRole.TEAM_AGENT, "team": self.team.id,
                "agent_role": AgentRole.DEFAULT,
            },
            context={"request": fake_request(self.boss)}
        )
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertFalse(user.has_usable_password())

    def test_create_with_phones(self):
        s = UserSerializer(
            data={
                "username": "ag4", "name": "Agent4",
                "role": UserRole.TEAM_AGENT, "team": self.team.id,
                "agent_role": AgentRole.DEFAULT,
                "phones": [{"phone_number": "01011111111"}, {"phone_number": "01022222222"}],
            },
            context={"request": fake_request(self.boss)}
        )
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertEqual(user.phones.count(), 2)

    def test_update_name(self):
        agent = make_user(
            UserRole.TEAM_AGENT, self.boss, branch=self.branch, team=self.team,
            username="ag5", agent_role=AgentRole.DEFAULT
        )
        s = UserSerializer(
            agent, data={"name": "Updated Name"}, partial=True,
            context={"request": fake_request(self.boss, method="PATCH")}
        )
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertEqual(user.name, "Updated Name")

    def test_update_replaces_phones(self):
        agent = make_user(
            UserRole.TEAM_AGENT, self.boss, branch=self.branch, team=self.team,
            username="ag6", agent_role=AgentRole.DEFAULT
        )
        UserPhone.objects.create(user=agent, phone_number="01011111111")
        s = UserSerializer(
            agent, data={"phones": [{"phone_number": "01099999999"}]}, partial=True,
            context={"request": fake_request(self.boss, method="PATCH")}
        )
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        phones = list(user.phones.values_list("phone_number", flat=True))
        self.assertEqual(phones, ["01099999999"])

    def test_output_includes_display_fields(self):
        agent = make_user(
            UserRole.TEAM_AGENT, self.boss, branch=self.branch, team=self.team,
            username="ag7", agent_role=AgentRole.DEFAULT
        )
        s = UserSerializer(agent)
        self.assertIn("role_display", s.data)
        self.assertIn("branch_name", s.data)
        self.assertIn("team_name", s.data)
        self.assertIn("creator_username", s.data)
        self.assertEqual(s.data["branch_name"], self.branch.name)
        self.assertEqual(s.data["team_name"], self.team.name)


# ===========================================================================
# EditLogSerializer
# ===========================================================================

class EditLogSerializerTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.agent = make_user(
            UserRole.TEAM_AGENT, self.boss, branch=self.branch, username="ag"
        )
        ct = ContentType.objects.get_for_model(self.agent)
        self.log = EditLog.objects.create(
            content_type=ct,
            object_id=self.agent.pk,
            editor=self.boss,
            description="Changed name",
        )

    def test_serializes_edit_log(self):
        s = EditLogSerializer(self.log)
        self.assertEqual(s.data["description"], "Changed name")
        self.assertEqual(s.data["editor"], self.boss.pk)
        self.assertEqual(s.data["editor_username"], self.boss.username)

    def test_content_type_name_is_model_name(self):
        s = EditLogSerializer(self.log)
        self.assertEqual(s.data["content_type_name"], "user")

    def test_object_id_matches(self):
        s = EditLogSerializer(self.log)
        self.assertEqual(s.data["object_id"], self.agent.pk)

    def test_edit_date_present(self):
        s = EditLogSerializer(self.log)
        self.assertIn("edit_date", s.data)
        self.assertIsNotNone(s.data["edit_date"])

    def test_read_only_fields_not_writable(self):
        s = EditLogSerializer(self.log)
        read_only = {f.field_name for f in s.fields.values() if f.read_only}
        self.assertIn("id", read_only)
        self.assertIn("edit_date", read_only)
        self.assertIn("editor", read_only)
