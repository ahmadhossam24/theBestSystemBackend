from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.db import IntegrityError

from .models import User, Branch, BranchPhone, Team, UserPhone, EditLog, UserRole, AgentRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_boss(**kwargs):
    """Create a company boss (no creator required)."""
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


# ===========================================================================
# UserRole / AgentRole choices
# ===========================================================================

class UserRoleChoicesTest(TestCase):
    def test_all_roles_present(self):
        values = [c[0] for c in UserRole.choices]
        self.assertIn("company_boss", values)
        self.assertIn("branch_admin", values)
        self.assertIn("team_admin", values)
        self.assertIn("team_agent", values)

    def test_default_agent_role_present(self):
        values = [c[0] for c in AgentRole.choices]
        self.assertIn("default", values)


# ===========================================================================
# User model
# ===========================================================================

class UserCreationTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)

    def test_company_boss_has_no_creator(self):
        self.assertIsNone(self.boss.creator)

    def test_default_role_is_team_agent(self):
        user = User.objects.create_user(
            username="plain", name="Plain", password="pass", creator=self.boss
        )
        self.assertEqual(user.role, UserRole.TEAM_AGENT)

    def test_branch_admin_creation(self):
        admin = make_user(UserRole.BRANCH_ADMIN, self.boss, branch=self.branch)
        self.assertEqual(admin.role, UserRole.BRANCH_ADMIN)
        self.assertEqual(admin.branch, self.branch)
        self.assertEqual(admin.creator, self.boss)

    def test_team_agent_with_agent_role(self):
        team = make_team(self.branch, self.boss)
        agent = make_user(
            UserRole.TEAM_AGENT, self.boss,
            branch=self.branch, team=team,
            agent_role=AgentRole.DEFAULT,
        )
        self.assertEqual(agent.agent_role, AgentRole.DEFAULT)

    def test_is_deleted_defaults_to_false(self):
        self.assertFalse(self.boss.is_deleted)

    def test_date_created_is_set_automatically(self):
        self.assertIsNotNone(self.boss.date_created)

    def test_str_representation(self):
        self.assertIn(self.boss.username, str(self.boss))
        self.assertIn("Company Boss", str(self.boss))


class UserSoftDeleteTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.agent = make_user(UserRole.TEAM_AGENT, self.boss, branch=self.branch)

    def test_soft_delete(self):
        self.agent.is_deleted = True
        self.agent.deleter = self.boss
        self.agent.date_deleted = timezone.now()
        self.agent.save()

        self.agent.refresh_from_db()
        self.assertTrue(self.agent.is_deleted)
        self.assertEqual(self.agent.deleter, self.boss)
        self.assertIsNotNone(self.agent.date_deleted)

    def test_soft_deleted_user_still_exists_in_db(self):
        self.agent.is_deleted = True
        self.agent.save()
        self.assertTrue(User.objects.filter(pk=self.agent.pk).exists())


class UserRelationshipsTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.team = make_team(self.branch, self.boss)
        self.agent = make_user(
            UserRole.TEAM_AGENT, self.boss,
            branch=self.branch, team=self.team,
        )

    def test_user_belongs_to_branch(self):
        self.assertEqual(self.agent.branch, self.branch)

    def test_user_belongs_to_team(self):
        self.assertEqual(self.agent.team, self.team)

    def test_branch_users_reverse_relation(self):
        self.assertIn(self.agent, self.branch.users.all())

    def test_team_users_reverse_relation(self):
        self.assertIn(self.agent, self.team.users.all())

    def test_creator_created_users_reverse_relation(self):
        self.assertIn(self.agent, self.boss.created_users.all())


# ===========================================================================
# Branch model
# ===========================================================================

class BranchModelTest(TestCase):
    def setUp(self):
        self.boss = make_boss()

    def test_branch_creation(self):
        branch = make_branch(self.boss, name="Downtown", location="City Center")
        self.assertEqual(branch.name, "Downtown")
        self.assertEqual(branch.location, "City Center")
        self.assertEqual(branch.creator, self.boss)

    def test_branch_name_unique(self):
        make_branch(self.boss, name="Unique Branch")
        with self.assertRaises(IntegrityError):
            make_branch(self.boss, name="Unique Branch")

    def test_branch_str(self):
        branch = make_branch(self.boss, name="East Branch")
        self.assertEqual(str(branch), "East Branch")

    def test_branch_soft_delete(self):
        branch = make_branch(self.boss)
        branch.is_deleted = True
        branch.deleter = self.boss
        branch.date_deleted = timezone.now()
        branch.save()

        branch.refresh_from_db()
        self.assertTrue(branch.is_deleted)
        self.assertEqual(branch.deleter, self.boss)

    def test_branch_default_is_not_deleted(self):
        branch = make_branch(self.boss)
        self.assertFalse(branch.is_deleted)

    def test_date_created_auto_set(self):
        branch = make_branch(self.boss)
        self.assertIsNotNone(branch.date_created)


# ===========================================================================
# BranchPhone model
# ===========================================================================

class BranchPhoneTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)

    def test_add_phone_to_branch(self):
        phone = BranchPhone.objects.create(branch=self.branch, phone_number="01012345678")
        self.assertEqual(phone.branch, self.branch)
        self.assertEqual(phone.phone_number, "01012345678")

    def test_duplicate_phone_per_branch_raises(self):
        BranchPhone.objects.create(branch=self.branch, phone_number="01012345678")
        with self.assertRaises(IntegrityError):
            BranchPhone.objects.create(branch=self.branch, phone_number="01012345678")

    def test_same_phone_different_branches_allowed(self):
        branch2 = make_branch(self.boss, name="Branch 2")
        BranchPhone.objects.create(branch=self.branch, phone_number="01099999999")
        # Should not raise
        BranchPhone.objects.create(branch=branch2, phone_number="01099999999")
        self.assertEqual(BranchPhone.objects.filter(phone_number="01099999999").count(), 2)

    def test_phones_reverse_relation(self):
        p = BranchPhone.objects.create(branch=self.branch, phone_number="01011111111")
        self.assertIn(p, self.branch.phones.all())

    def test_str_representation(self):
        p = BranchPhone.objects.create(branch=self.branch, phone_number="01011111111")
        self.assertIn(self.branch.name, str(p))
        self.assertIn("01011111111", str(p))

    def test_cascade_delete_with_branch(self):
        BranchPhone.objects.create(branch=self.branch, phone_number="01011111111")
        branch_id = self.branch.id
        self.branch.delete()
        self.assertEqual(BranchPhone.objects.filter(branch_id=branch_id).count(), 0)


# ===========================================================================
# Team model
# ===========================================================================

class TeamModelTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)

    def test_team_creation(self):
        team = make_team(self.branch, self.boss, name="Sales")
        self.assertEqual(team.name, "Sales")
        self.assertEqual(team.branch, self.branch)
        self.assertEqual(team.creator, self.boss)

    def test_team_name_unique_within_branch(self):
        make_team(self.branch, self.boss, name="Sales")
        with self.assertRaises(IntegrityError):
            make_team(self.branch, self.boss, name="Sales")

    def test_same_team_name_different_branches_allowed(self):
        branch2 = make_branch(self.boss, name="Branch 2")
        make_team(self.branch, self.boss, name="Sales")
        team2 = make_team(branch2, self.boss, name="Sales")
        self.assertEqual(team2.name, "Sales")

    def test_team_str(self):
        team = make_team(self.branch, self.boss, name="Support")
        self.assertIn(self.branch.name, str(team))
        self.assertIn("Support", str(team))

    def test_team_soft_delete(self):
        team = make_team(self.branch, self.boss)
        team.is_deleted = True
        team.deleter = self.boss
        team.date_deleted = timezone.now()
        team.save()

        team.refresh_from_db()
        self.assertTrue(team.is_deleted)

    def test_teams_reverse_relation_on_branch(self):
        team = make_team(self.branch, self.boss)
        self.assertIn(team, self.branch.teams.all())

    def test_date_created_auto_set(self):
        team = make_team(self.branch, self.boss)
        self.assertIsNotNone(team.date_created)


# ===========================================================================
# UserPhone model
# ===========================================================================

class UserPhoneTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.agent = make_user(UserRole.TEAM_AGENT, self.boss, branch=self.branch)

    def test_add_phone_to_user(self):
        phone = UserPhone.objects.create(user=self.agent, phone_number="01055555555")
        self.assertEqual(phone.user, self.agent)

    def test_duplicate_phone_per_user_raises(self):
        UserPhone.objects.create(user=self.agent, phone_number="01055555555")
        with self.assertRaises(IntegrityError):
            UserPhone.objects.create(user=self.agent, phone_number="01055555555")

    def test_same_phone_different_users_allowed(self):
        agent2 = make_user(UserRole.TEAM_AGENT, self.boss, branch=self.branch)
        UserPhone.objects.create(user=self.agent, phone_number="01055555555")
        UserPhone.objects.create(user=agent2, phone_number="01055555555")
        self.assertEqual(UserPhone.objects.filter(phone_number="01055555555").count(), 2)

    def test_phones_reverse_relation(self):
        p = UserPhone.objects.create(user=self.agent, phone_number="01055555555")
        self.assertIn(p, self.agent.phones.all())

    def test_str_representation(self):
        p = UserPhone.objects.create(user=self.agent, phone_number="01055555555")
        self.assertIn(self.agent.username, str(p))
        self.assertIn("01055555555", str(p))

    def test_cascade_delete_with_user(self):
        UserPhone.objects.create(user=self.agent, phone_number="01055555555")
        agent_id = self.agent.id
        self.agent.delete()
        self.assertEqual(UserPhone.objects.filter(user_id=agent_id).count(), 0)


# ===========================================================================
# EditLog model
# ===========================================================================

class EditLogTest(TestCase):
    def setUp(self):
        self.boss = make_boss()
        self.branch = make_branch(self.boss)
        self.agent = make_user(UserRole.TEAM_AGENT, self.boss, branch=self.branch)

    def _log_edit(self, obj, editor, description="Changed name"):
        ct = ContentType.objects.get_for_model(obj)
        return EditLog.objects.create(
            content_type=ct,
            object_id=obj.pk,
            editor=editor,
            description=description,
        )

    def test_create_edit_log_for_user(self):
        log = self._log_edit(self.agent, self.boss, "Updated agent name")
        self.assertEqual(log.editor, self.boss)
        self.assertEqual(log.content_object, self.agent)
        self.assertEqual(log.description, "Updated agent name")

    def test_create_edit_log_for_branch(self):
        log = self._log_edit(self.branch, self.boss, "Updated branch location")
        self.assertEqual(log.content_object, self.branch)

    def test_create_edit_log_for_team(self):
        team = make_team(self.branch, self.boss)
        log = self._log_edit(team, self.boss, "Renamed team")
        self.assertEqual(log.content_object, team)

    def test_edit_date_auto_set(self):
        log = self._log_edit(self.agent, self.boss)
        self.assertIsNotNone(log.edit_date)

    def test_edit_log_str(self):
        log = self._log_edit(self.agent, self.boss)
        self.assertIn(self.boss.username, str(log))

    def test_generic_relation_on_user(self):
        log = self._log_edit(self.agent, self.boss)
        self.assertIn(log, self.agent.edits.all())

    def test_generic_relation_on_branch(self):
        log = self._log_edit(self.branch, self.boss)
        self.assertIn(log, self.branch.edits.all())

    def test_multiple_logs_for_same_object(self):
        self._log_edit(self.agent, self.boss, "First change")
        self._log_edit(self.agent, self.boss, "Second change")
        self.assertEqual(self.agent.edits.count(), 2)

    def test_edits_made_reverse_relation(self):
        log = self._log_edit(self.agent, self.boss)
        self.assertIn(log, self.boss.edits_made.all())
