from datetime import timedelta
from unittest.mock import patch
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework import status
from rest_framework.test import APITestCase

from .apps import check_custom_user_schema_compatibility
from .models import Collection, Event, Kudos, Profile, SkillCategory, Team, TeamMembership


User = get_user_model()


def create_project_user(*, email, password="StrongPass123!", **extra_fields):
    """Create a test user using email as the project's login identifier."""
    return User.objects.create_user(
        password=password,
        email=email,
        **extra_fields,
    )


def create_project_superuser(*, email, password="StrongPass123!", **extra_fields):
    """Create a test superuser using email as the project's login identifier."""
    return User.objects.create_superuser(
        password=password,
        email=email,
        **extra_fields,
    )


class TeamModelSetupTests(TestCase):
    def test_default_teams_are_seeded(self):
        """Verify the required default team records exist after migrations run."""
        expected_names = {
            "Account Management",
            "Sales",
            "Tech",
            "Management",
            "Administration",
        }

        self.assertTrue(expected_names.issubset(set(Team.objects.values_list("name", flat=True))))

    def test_custom_user_deployment_check_flags_legacy_auth_user_schema(self):
        """Verify deployment checks catch legacy databases without the custom user table."""
        legacy_connection = type(
            "LegacyConnection",
            (),
            {"introspection": type("Introspection", (), {"table_names": lambda self: ["auth_user"]})()},
        )()
        with patch(
            "accounts.apps.connections",
            {"default": legacy_connection},
        ):
            errors = check_custom_user_schema_compatibility(None, databases=["default"])

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "accounts.E001")
        self.assertEqual(errors[0].obj, "database:default")

    def test_custom_user_deployment_check_allows_custom_user_schema(self):
        """Verify deployment checks pass when the custom user table is present."""
        custom_connection = type(
            "CustomConnection",
            (),
            {"introspection": type("Introspection", (), {"table_names": lambda self: ["accounts_user"]})()},
        )()
        with patch(
            "accounts.apps.connections",
            {"default": custom_connection},
        ):
            errors = check_custom_user_schema_compatibility(None, databases=["default"])

        self.assertEqual(errors, [])

    def test_custom_user_save_mirrors_into_legacy_auth_user_when_table_exists(self):
        """Verify new custom users keep an auth_user mirror for legacy FK compatibility."""
        self.addCleanup(self._drop_legacy_auth_user_table)
        with connections["default"].cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE auth_user (
                    id INTEGER NOT NULL PRIMARY KEY,
                    password varchar(128) NOT NULL,
                    last_login datetime NULL,
                    is_superuser bool NOT NULL,
                    username varchar(150) NOT NULL,
                    last_name varchar(150) NOT NULL,
                    email varchar(254) NOT NULL,
                    is_staff bool NOT NULL,
                    is_active bool NOT NULL,
                    date_joined datetime NOT NULL,
                    first_name varchar(150) NOT NULL
                )
                """
            )

        user = create_project_user(
            email="legacy_mirror+pp@gmail.com",
            first_name="Legacy",
            last_name="Mirror",
        )

        with connections["default"].cursor() as cursor:
            cursor.execute(
                "SELECT username, email, first_name, last_name FROM auth_user WHERE id = %s",
                [user.id],
            )
            row = cursor.fetchone()

        self.assertEqual(
            row,
            ("legacy_mirror+pp@gmail.com", "legacy_mirror+pp@gmail.com", "Legacy", "Mirror"),
        )

    def _drop_legacy_auth_user_table(self):
        with connections["default"].cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS auth_user")

    def test_default_skills_are_seeded(self):
        """Verify the required default skill records exist after migrations run."""
        expected_names = {
            "Sales",
            "Account Management",
            "Lead Generation",
            "Communication",
            "Project Management",
            "Business Administration",
            "Reporting",
            "Website Development",
        }

        self.assertTrue(
            expected_names.issubset(set(SkillCategory.objects.values_list("name", flat=True)))
        )

    def test_default_skill_normalization_reactivates_existing_required_skills(self):
        """Verify normalization fixes inactive/default-skill drift on existing rows."""
        sales_skill = SkillCategory.objects.get(name="Sales")
        sales_skill.slug = "old-sales"
        sales_skill.description = "Outdated description"
        sales_skill.is_active = False
        sales_skill.save(update_fields=["slug", "description", "is_active"])

        normalize_module = import_module("accounts.migrations.0012_normalize_default_skills")
        normalize_module.normalize_default_skills(django_apps, None)

        sales_skill.refresh_from_db()
        self.assertEqual(sales_skill.slug, "sales")
        self.assertEqual(sales_skill.description, "Sales skill")
        self.assertTrue(sales_skill.is_active)


class AdminUserManagementTests(TestCase):
    def setUp(self):
        """Create an admin user and a target user for Django admin management tests."""
        self.admin_user = create_project_superuser(
            email="site_admin@example.com",
        )
        self.target_user = create_project_user(
            email="managed_user@example.com",
            first_name="Managed",
            last_name="Person",
            is_active=True,
        )
        self.client.force_login(self.admin_user)

    def test_user_model_uses_project_admin_registration(self):
        """Verify user management is explicitly configured in the project admin."""
        registered_admin = site._registry[User]

        self.assertIn("is_active", registered_admin.list_display)
        self.assertIn("email", registered_admin.search_fields)

    def test_admin_user_changelist_shows_users(self):
        """Verify admins can open the user list in Django admin."""
        response = self.client.get(reverse("admin:accounts_user_changelist"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Managed")
        self.assertContains(response, "Person")
        self.assertContains(response, "managed_user@example.com")

    def test_admin_can_update_user_active_state(self):
        """Verify admins can change a user from active to inactive in admin."""
        change_url = reverse("admin:accounts_user_change", args=[self.target_user.pk])
        response = self.client.post(
            change_url,
            {
                "email": self.target_user.email,
                "first_name": self.target_user.first_name,
                "last_name": self.target_user.last_name,
                "password": self.target_user.password,
                "is_active": "",
                "is_staff": "",
                "is_superuser": "",
                "groups": [],
                "user_permissions": [],
                "last_login_0": "",
                "last_login_1": "",
                "date_joined_0": self.target_user.date_joined.strftime("%Y-%m-%d"),
                "date_joined_1": self.target_user.date_joined.strftime("%H:%M:%S"),
                "_save": "Save",
                "profile-TOTAL_FORMS": "0",
                "profile-INITIAL_FORMS": "0",
                "profile-MIN_NUM_FORMS": "0",
                "profile-MAX_NUM_FORMS": "1",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)

    def test_admin_can_access_event_and_collection_management(self):
        """Verify Django admin exposes event and collection changelists."""
        event = Event.objects.create(
            name="Quarterly Celebration",
            slug="quarterly-celebration",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=2),
            is_active=True,
        )
        collection = Collection.objects.create(
            name="Top Kudos",
            slug="top-kudos",
            is_active=True,
        )

        event_response = self.client.get(reverse("admin:accounts_event_changelist"))
        collection_response = self.client.get(reverse("admin:accounts_collection_changelist"))

        self.assertEqual(event_response.status_code, status.HTTP_200_OK)
        self.assertContains(event_response, event.name)
        self.assertEqual(collection_response.status_code, status.HTTP_200_OK)
        self.assertContains(collection_response, collection.name)


class UserAccountViewTests(APITestCase):
    def setUp(self):
        """Prepare shared fixtures for user-account endpoint tests.

        This creates one authenticated user and stores the `/auth/user/` URL used
        by PATCH and DELETE test scenarios.
        """
        self.user = create_project_user(
            email="patch_delete_user@example.com",
            first_name="Before",
        )
        self.url = "/auth/user/"

    def test_patch_user_updates_profile_fields(self):
        """Verify PATCH updates mutable user fields and response payload values.

        Covers:
            - authenticated patch request
            - database value update
            - response body consistency
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            self.url,
            {"first_name": "After"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "After")
        self.assertEqual(response.data["user"]["first_name"], "After")

    def test_delete_user_without_kudos_returns_204(self):
        """Verify DELETE succeeds when no protected kudos relations exist.

        Expected behavior:
            - endpoint returns 204
            - user record is removed from database
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_delete_user_with_kudos_returns_409_and_keeps_user(self):
        """Verify DELETE is blocked by PROTECT constraints from related kudos.

        Expected behavior:
            - endpoint returns 409 conflict
            - response includes explanatory detail message
            - user record remains in database
        """
        recipient = create_project_user(
            email="patch_delete_recipient@example.com",
        )
        Kudos.objects.create(
            sender=self.user,
            recipient=recipient,
            message="protected by kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("Cannot delete user", response.data["detail"])
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_post_user_requires_authentication(self):
        """Verify anonymous account creation is blocked."""
        response = self.client.post(
            self.url,
            {
                "email": "new_user@example.com",
                "first_name": "New",
                "last_name": "User",
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
            },
            format="json",
        )

        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )


class AuthenticationAccessTests(APITestCase):
    def setUp(self):
        """Create a user and URLs used to verify anonymous access rules."""
        self.user = create_project_user(
            email="login_user@example.com",
        )
        self.login_url = "/auth/login/"
        self.signup_url = "/auth/signup/"
        self.public_kudos_url = "/api/kudos/public/"
        self.user_received_kudos_url = f"/api/users/{self.user.id}/received-kudos/"
        self.user_given_kudos_url = f"/api/users/{self.user.id}/given-kudos/"

    def test_login_allows_anonymous_access(self):
        """Verify login remains the only anonymous auth endpoint."""
        response = self.client.post(
            self.login_url,
            {"email": self.user.email, "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["token"], Token.objects.get(user=self.user).key)
        self.assertEqual(
            response.data["user"]["snapshot"],
            {"kudos_given": 0, "kudos_received": 0},
        )

    def test_invalid_login_returns_error_for_json_clients(self):
        """Verify invalid JSON login returns a validation error instead of redirecting."""
        response = self.client.post(
            self.login_url,
            {"email": self.user.email, "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)

    def test_invalid_login_renders_error_for_browser_requests(self):
        """Verify invalid browser login keeps the user on the login page with an error."""
        response = self.client.post(
            self.login_url,
            {"email": self.user.email, "password": "wrong-password"},
            HTTP_ACCEPT="text/html",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertContains(response, "Invalid email or password.", status_code=400)

    def test_login_page_renders_for_browser_requests(self):
        """Verify browser requests can load the backend login page."""
        response = self.client.get(self.login_url, HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Log in")

    def test_signup_allows_anonymous_access(self):
        """Verify signup is available to anonymous users."""
        response = self.client.post(
            self.signup_url,
            {
                "email": "signup_user+pp@gmail.com",
                "first_name": "Signup",
                "last_name": "User",
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["email"], "signup_user+pp@gmail.com")
        self.assertTrue(response.data["user"]["is_active"])
        self.assertEqual(response.data["user"]["first_name"], "Signup")
        self.assertEqual(response.data["user"]["last_name"], "User")

    def test_public_kudos_feed_requires_authentication(self):
        """Verify anonymous users cannot access the read-only kudos feed."""
        response = self.client.get(self.public_kudos_url)

        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_user_received_and_given_kudos_endpoints_require_authentication(self):
        """Verify user-specific kudos endpoints require authentication."""
        received_response = self.client.get(self.user_received_kudos_url)
        given_response = self.client.get(self.user_given_kudos_url)

        self.assertIn(
            received_response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )
        self.assertIn(
            given_response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_browser_requests_redirect_to_login_page(self):
        """Verify unauthorized browser navigation redirects to login."""
        response = self.client.get("/auth/profile/", HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response["Location"], "/auth/login/?next=%2Fauth%2Fprofile%2F")

    def test_api_requests_do_not_redirect_to_login_page(self):
        """Verify API clients get auth errors instead of HTML redirects."""
        response = self.client.get("/auth/profile/", HTTP_ACCEPT="application/json")

        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

    def test_browser_login_redirects_back_to_requested_page(self):
        """Verify the HTML login form can return the user to the original path."""
        response = self.client.post(
            f"{self.login_url}?next=/auth/profile/",
            {
                "email": self.user.email,
                "password": "StrongPass123!",
                "next": "/auth/profile/",
            },
            HTTP_ACCEPT="text/html",
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response["Location"], "/auth/profile/")


class ForgotPasswordViewTests(APITestCase):
    def setUp(self):
        self.user = create_project_user(
            email="forgot_password_user@example.com",
            first_name="Forgot",
        )
        self.url = "/auth/forgot-password/"

    @override_settings(
        EMAIL_HOST_USER=None,
        EMAIL_HOST_PASSWORD=None,
        DEFAULT_FROM_EMAIL=None,
    )
    @patch("accounts.views.send_mail")
    def test_forgot_password_returns_200_when_email_config_missing(self, mock_send_mail):
        response = self.client.post(
            self.url,
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("If an account exists", response.data["message"])
        mock_send_mail.assert_not_called()

    @override_settings(
        EMAIL_HOST_USER="ruffactor.app@gmail.com",
        EMAIL_HOST_PASSWORD="app-password",
        DEFAULT_FROM_EMAIL="ruffactor.app@gmail.com",
    )
    @patch("accounts.views.send_mail", side_effect=Exception("smtp failure"))
    def test_forgot_password_returns_200_when_email_send_fails(self, mock_send_mail):
        response = self.client.post(
            self.url,
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("If an account exists", response.data["message"])
        mock_send_mail.assert_called_once()


class SignUpTeamSelectionTests(APITestCase):
    def setUp(self):
        """Create an authenticated requester and teams for signup flow tests."""
        self.request_user = create_project_user(
            email="signup_requester@example.com",
        )
        self.team = Team.objects.create(
            name="Engineering",
            slug="engineering",
            description="Engineering team",
        )
        self.signup_url = "/auth/signup/"
        self.client.force_authenticate(user=self.request_user)

    def test_signup_allows_missing_team_selection(self):
        """Verify signup succeeds when no team is selected."""
        response = self.client.post(
            self.signup_url,
            {
                "email": "new_teamless_user+pp@gmail.com",
                "first_name": "Teamless",
                "last_name": "User",
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="new_teamless_user+pp@gmail.com")
        created_profile, _ = Profile.objects.get_or_create(user=created_user)

        self.assertIsNone(created_profile.active_team_id)
        self.assertFalse(TeamMembership.objects.filter(user=created_user).exists())
        self.assertTrue(created_user.is_active)
        self.assertEqual(created_user.email, "new_teamless_user+pp@gmail.com")

    def test_signup_saves_selected_team_to_profile_and_membership(self):
        """Verify signup persists the selected team on the user profile."""
        response = self.client.post(
            self.signup_url,
            {
                "email": "new_team_user+pp@gmail.com",
                "first_name": "New",
                "last_name": "Member",
                "team_id": self.team.id,
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="new_team_user+pp@gmail.com")
        created_profile = Profile.objects.get(user=created_user)

        self.assertEqual(created_profile.active_team_id, self.team.id)
        self.assertTrue(
            TeamMembership.objects.filter(user=created_user, team=self.team).exists()
        )

    def test_signup_rolls_back_user_when_team_setup_fails(self):
        """Verify signup does not leave a partial user record if team setup crashes."""
        with patch(
            "accounts.serializers.TeamMembership.objects.get_or_create",
            side_effect=RuntimeError("team setup failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.signup_url,
                    {
                        "email": "rollback_user+pp@gmail.com",
                        "first_name": "Rollback",
                        "last_name": "User",
                        "team_id": self.team.id,
                        "password": "StrongPass123!",
                        "confirm_password": "StrongPass123!",
                    },
                    format="json",
                )

        self.assertFalse(User.objects.filter(email="rollback_user+pp@gmail.com").exists())

    def test_signup_rejects_non_pixel_pulse_email(self):
        """Verify signup requires the approved +pp@gmail.com email suffix."""
        response = self.client.post(
            self.signup_url,
            {
                "email": "outside_user@example.com",
                "first_name": "Outside",
                "last_name": "User",
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_signup_requires_first_name_and_last_name(self):
        """Verify signup rejects requests missing mandatory names."""
        response = self.client.post(
            self.signup_url,
            {
                "email": "missing_names+pp@gmail.com",
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("first_name", response.data)
        self.assertIn("last_name", response.data)


class UserAccountEmailPolicyTests(APITestCase):
    def setUp(self):
        """Create a logged-in user for profile email policy checks."""
        self.user = create_project_user(
            email="pixelpulse_user+pp@gmail.com",
        )

    def test_profile_update_rejects_non_pixel_pulse_email(self):
        """Verify users cannot change their profile email outside the approved suffix."""
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            "/auth/user/",
            {"email": "new_email@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)


class TeamMembershipRuleTests(APITestCase):
    def setUp(self):
        """Create users and teams used to verify one-team-per-user enforcement."""
        self.staff = create_project_user(
            email="team_admin@example.com",
            is_staff=True,
        )
        self.member = create_project_user(
            email="team_member@example.com",
        )
        self.sales_team = Team.objects.create(
            name="Regional Sales",
            slug="regional-sales",
            description="Regional sales team",
        )
        self.tech_team = Team.objects.create(
            name="Platform Tech",
            slug="platform-tech",
            description="Platform tech team",
        )
        TeamMembership.objects.create(
            user=self.member,
            team=self.sales_team,
            role=TeamMembership.Role.MEMBER,
        )
        profile, _ = Profile.objects.get_or_create(user=self.member)
        profile.active_team = self.sales_team
        profile.save(update_fields=["active_team", "updated_at"])

    def test_add_member_allows_multiple_team_memberships(self):
        """Verify assigning a new team adds membership without removing existing teams."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            f"/api/teams/{self.tech_team.id}/members/",
            {
                "user_id": self.member.id,
                "role": TeamMembership.Role.MEMBER,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TeamMembership.objects.filter(user=self.member).count(), 2)
        self.assertTrue(
            TeamMembership.objects.filter(user=self.member, team=self.sales_team).exists()
        )
        self.assertTrue(
            TeamMembership.objects.filter(user=self.member, team=self.tech_team).exists()
        )
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.active_team_id, self.sales_team.id)


class KudosApiTicketTests(APITestCase):
    def setUp(self):
        """Prepare shared fixtures for kudos API ticket coverage.

        This creates sender/recipient/viewer/staff users, active and inactive skills,
        and stores the base `/api/kudos/` endpoint URL.
        """
        self.sender = create_project_user(
            email="kudos_sender@example.com",
        )
        self.recipient = create_project_user(
            email="kudos_recipient@example.com",
        )
        self.viewer = create_project_user(
            email="kudos_viewer@example.com",
        )
        self.staff = create_project_user(
            email="kudos_staff@example.com",
            is_staff=True,
        )
        self.extra_recipient_one = create_project_user(
            email="kudos_extra_one@example.com",
        )
        self.extra_recipient_two = create_project_user(
            email="kudos_extra_two@example.com",
        )
        self.extra_recipient_three = create_project_user(
            email="kudos_extra_three@example.com",
        )
        self.skill = SkillCategory.objects.create(
            name="Teamwork",
            slug="teamwork",
            is_active=True,
        )
        self.team = Team.objects.create(
            name="Product",
            slug="product",
            description="Product team",
        )
        self.other_team = Team.objects.create(
            name="Operations",
            slug="operations",
            description="Operations team",
        )
        TeamMembership.objects.create(
            team=self.team,
            user=self.sender,
            role=TeamMembership.Role.MEMBER,
        )
        self.inactive_skill = SkillCategory.objects.create(
            name="Legacy",
            slug="legacy",
            is_active=False,
        )
        self.extra_skill_one = SkillCategory.objects.create(
            name="Planning",
            slug="planning",
            is_active=True,
        )
        self.extra_skill_two = SkillCategory.objects.create(
            name="Execution",
            slug="execution",
            is_active=True,
        )
        self.extra_skill_three = SkillCategory.objects.create(
            name="Coaching",
            slug="coaching",
            is_active=True,
        )
        self.extra_skill_four = SkillCategory.objects.create(
            name="Strategy",
            slug="strategy",
            is_active=True,
        )
        self.extra_skill_five = SkillCategory.objects.create(
            name="Analysis",
            slug="analysis",
            is_active=True,
        )
        self.kudos_url = "/api/kudos/"
        self.public_kudos_url = "/api/kudos/public/"
        self.received_kudos_url = f"/api/users/{self.recipient.id}/received-kudos/"
        self.given_kudos_url = f"/api/users/{self.sender.id}/given-kudos/"

    def test_post_kudos_requires_at_least_one_predefined_skill(self):
        """Verify kudos creation fails when `skill_ids` is missing.

        Expected behavior:
            - endpoint returns 400
            - validation error is attached to `skill_ids`
        """
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient": self.recipient.id,
                "message": "Great collaboration!",
                "visibility": Kudos.Visibility.PUBLIC,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("skill_ids", response.data)

    def test_post_kudos_uses_authenticated_sender_and_predefined_skill(self):
        """Verify kudos creation uses authenticated sender and active skill tags.

        Expected behavior:
            - endpoint returns 201
            - sender in response matches authenticated user
            - selected skill is persisted and returned
        """
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient": self.recipient.id,
                "message": "Thanks for your support",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [self.skill.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["sender"]["id"], self.sender.id)
        self.assertEqual(response.data["recipient"]["id"], self.recipient.id)
        self.assertEqual(response.data["message"], "Thanks for your support")
        self.assertEqual([item["id"] for item in response.data["skills"]], [self.skill.id])

    def test_post_kudos_can_save_multiple_individual_recipients(self):
        """Verify kudos creation accepts multiple individual recipients."""
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient_ids": [self.recipient.id, self.viewer.id],
                "message": "Thanks to both of you",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [self.skill.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["recipient"]["id"], self.recipient.id)
        self.assertEqual(
            [item["id"] for item in response.data["recipients"]],
            [self.recipient.id, self.viewer.id],
        )

    def test_post_kudos_rejects_more_than_five_recipients(self):
        """Verify kudos creation returns a validation error when recipient count exceeds 5."""
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient_ids": [
                    self.recipient.id,
                    self.viewer.id,
                    self.staff.id,
                    self.extra_recipient_one.id,
                    self.extra_recipient_two.id,
                    self.extra_recipient_three.id,
                ],
                "message": "Too many recipients",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [self.skill.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["recipient_ids"][0],
            "You can select up to 5 recipients per kudos.",
        )

    def test_profile_includes_snapshot_counts(self):
        """Verify profile payload includes aggregate kudos given and received totals."""
        sent_kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Sent kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        sent_kudos.skills.set([self.skill])
        received_kudos = Kudos.objects.create(
            sender=self.viewer,
            recipient=self.sender,
            message="Received kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        received_kudos.skills.set([self.skill])

        self.client.force_authenticate(user=self.sender)
        response = self.client.get("/auth/profile/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["snapshot"],
            {"kudos_given": 1, "kudos_received": 1},
        )

    def test_kudos_snapshot_endpoint_returns_updated_counts(self):
        """Verify the home snapshot endpoint returns current non-archived totals."""
        current = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Current sent kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        current.skills.set([self.skill])
        received = Kudos.objects.create(
            sender=self.viewer,
            recipient=self.sender,
            message="Current received kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        received.skills.set([self.skill])
        archived = Kudos.objects.create(
            sender=self.sender,
            recipient=self.viewer,
            message="Archived kudos should not count",
            visibility=Kudos.Visibility.PUBLIC,
            is_archived=True,
        )
        archived.skills.set([self.skill])

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(f"{self.kudos_url}snapshot/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"kudos_given": 1, "kudos_received": 1},
        )

    def test_snapshot_counts_secondary_recipient_from_multi_recipient_kudos(self):
        """Verify a non-primary recipient still receives snapshot credit."""
        self.client.force_authenticate(user=self.sender)
        create_response = self.client.post(
            self.kudos_url,
            {
                "recipient_ids": [self.recipient.id, self.viewer.id],
                "message": "Thanks to both recipients",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [self.skill.id],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(f"{self.kudos_url}snapshot/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"kudos_given": 0, "kudos_received": 1},
        )

    def test_post_kudos_rejects_inactive_skill_tag(self):
        """Verify kudos creation rejects inactive skill IDs.

        Expected behavior:
            - endpoint returns 400
            - validation error is attached to `skill_ids`
        """
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient": self.recipient.id,
                "message": "This should fail",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [self.inactive_skill.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("skill_ids", response.data)

    def test_post_kudos_rejects_more_than_five_skills(self):
        """Verify kudos creation returns a validation error when skill count exceeds 5."""
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient": self.recipient.id,
                "message": "Too many skills selected",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [
                    self.skill.id,
                    self.extra_skill_one.id,
                    self.extra_skill_two.id,
                    self.extra_skill_three.id,
                    self.extra_skill_four.id,
                    self.extra_skill_five.id,
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["skill_ids"][0],
            "You can select up to 5 skills per kudos.",
        )

    def test_post_kudos_allows_duplicate_skill_ids_when_unique_count_is_five(self):
        """Verify duplicate submitted skills do not count against the 5-skill limit."""
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient": self.recipient.id,
                "message": "Duplicate skills should be deduplicated",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [
                    self.skill.id,
                    self.skill.id,
                    self.extra_skill_one.id,
                    self.extra_skill_two.id,
                    self.extra_skill_three.id,
                    self.extra_skill_four.id,
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["skills"]), 5)

    def test_post_kudos_can_save_and_display_team_tag(self):
        """Verify team tags can be attached and returned on kudos responses."""
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient": self.recipient.id,
                "message": "Thanks, Product team",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [self.skill.id],
                "target_team_ids": [self.team.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual([item["id"] for item in response.data["target_teams"]], [self.team.id])
        self.assertEqual(response.data["target_teams"][0]["name"], self.team.name)

    def test_post_kudos_rejects_team_tag_for_non_member(self):
        """Verify non-staff users cannot tag teams they do not belong to."""
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient": self.recipient.id,
                "message": "I should not be able to tag this team",
                "visibility": Kudos.Visibility.PUBLIC,
                "skill_ids": [self.skill.id],
                "target_team_ids": [self.other_team.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_team_ids", response.data)

    def test_patch_kudos_updates_team_tag_and_displays_it(self):
        """Verify team tags can be updated and returned in the updated payload."""
        kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Initial team tag",
            visibility=Kudos.Visibility.PUBLIC,
        )
        kudos.skills.set([self.skill])
        kudos.target_teams.set([self.team])
        TeamMembership.objects.filter(user=self.sender).update(team=self.other_team)
        sender_profile, _ = Profile.objects.get_or_create(user=self.sender)
        sender_profile.active_team = self.other_team
        sender_profile.save(update_fields=["active_team", "updated_at"])

        self.client.force_authenticate(user=self.sender)
        response = self.client.patch(
            f"{self.kudos_url}{kudos.id}/",
            {
                "target_team_ids": [self.other_team.id],
                "skill_ids": [self.skill.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data["target_teams"]],
            [self.other_team.id],
        )

    def test_team_visibility_still_requires_at_least_one_team_tag(self):
        """Verify team-visible kudos still require at least one tagged team."""
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(
            self.kudos_url,
            {
                "recipient": self.recipient.id,
                "message": "Missing tagged team",
                "visibility": Kudos.Visibility.TEAM,
                "skill_ids": [self.skill.id],
                "target_team_ids": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_team_ids", response.data)

    def test_home_search_by_sender_and_recipient_returns_latest_first(self):
        """Verify sender/recipient search filters and default latest-first ordering.

        Expected behavior:
            - filtered list returns only matching records
            - newest record appears before older record
        """
        older = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Older kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        older.skills.set([self.skill])
        newer = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Newer kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        newer.skills.set([self.skill])
        now = timezone.now()
        Kudos.objects.filter(pk=older.pk).update(created_at=now - timedelta(days=1))
        Kudos.objects.filter(pk=newer.pk).update(created_at=now)

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(
            f"{self.kudos_url}?sender={self.sender.id}&recipient={self.recipient.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["id"], newer.id)
        self.assertEqual(response.data["results"][1]["id"], older.id)

    def test_user_received_kudos_endpoint_includes_secondary_recipients(self):
        """Verify user received-kudos endpoint includes multi-recipient kudos."""
        primary = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Primary recipient kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        primary.recipients.set([self.recipient])
        primary.skills.set([self.skill])

        secondary = Kudos.objects.create(
            sender=self.viewer,
            recipient=self.staff,
            message="Secondary recipient kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        secondary.recipients.set([self.staff, self.recipient])
        secondary.skills.set([self.skill])

        self.client.force_authenticate(user=self.recipient)
        response = self.client.get(self.received_kudos_url)
        result_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(primary.id, result_ids)
        self.assertIn(secondary.id, result_ids)

    def test_user_given_kudos_endpoint_returns_latest_first(self):
        """Verify user given-kudos endpoint returns sender history newest first."""
        older = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Older given kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        older.recipients.set([self.recipient])
        older.skills.set([self.skill])
        newer = Kudos.objects.create(
            sender=self.sender,
            recipient=self.viewer,
            message="Newer given kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        newer.recipients.set([self.viewer])
        newer.skills.set([self.skill])
        now = timezone.now()
        Kudos.objects.filter(pk=older.pk).update(created_at=now - timedelta(days=1))
        Kudos.objects.filter(pk=newer.pk).update(created_at=now)

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.given_kudos_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["id"], newer.id)
        self.assertEqual(response.data["results"][1]["id"], older.id)

    def test_feed_only_returns_kudos_from_current_month(self):
        """Verify the main feed excludes kudos outside the current calendar month."""
        now = timezone.now()
        current_month_kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Current month kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        current_month_kudos.skills.set([self.skill])

        previous_month_kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Previous month kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        previous_month_kudos.skills.set([self.skill])

        if now.month == 1:
            previous_month = now.replace(year=now.year - 1, month=12, day=15)
        else:
            previous_month = now.replace(month=now.month - 1, day=15)

        next_month = (
            now.replace(year=now.year + 1, month=1, day=1)
            if now.month == 12
            else now.replace(month=now.month + 1, day=1)
        )

        Kudos.objects.filter(pk=current_month_kudos.pk).update(
            created_at=now.replace(day=min(now.day, 15))
        )
        Kudos.objects.filter(pk=previous_month_kudos.pk).update(created_at=previous_month)

        future_kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Future month kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        future_kudos.skills.set([self.skill])
        Kudos.objects.filter(pk=future_kudos.pk).update(created_at=next_month)

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.kudos_url)
        result_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(current_month_kudos.id, result_ids)
        self.assertNotIn(previous_month_kudos.id, result_ids)
        self.assertNotIn(future_kudos.id, result_ids)

    def test_public_feed_only_returns_current_month_kudos(self):
        """Verify the public feed applies the same current-month window."""
        now = timezone.now()
        current_month_kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Public current month kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        current_month_kudos.skills.set([self.skill])

        old_public_kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Old public kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        old_public_kudos.skills.set([self.skill])

        boundary_previous_month = (
            now.replace(year=now.year - 1, month=12, day=28)
            if now.month == 1
            else now.replace(month=now.month - 1, day=28)
        )

        Kudos.objects.filter(pk=old_public_kudos.pk).update(created_at=boundary_previous_month)

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.public_kudos_url)
        result_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(current_month_kudos.id, result_ids)
        self.assertNotIn(old_public_kudos.id, result_ids)

    def test_home_search_query_matches_sender_and_recipient_text(self):
        """Verify general home search can find kudos by people fields, not just message."""
        sender_match = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Message without search term",
            visibility=Kudos.Visibility.PUBLIC,
        )
        sender_match.skills.set([self.skill])
        recipient_match = Kudos.objects.create(
            sender=self.viewer,
            recipient=self.recipient,
            message="Another message without name text",
            visibility=Kudos.Visibility.PUBLIC,
        )
        recipient_match.skills.set([self.skill])
        unrelated = Kudos.objects.create(
            sender=self.viewer,
            recipient=self.staff,
            message="Completely unrelated post",
            visibility=Kudos.Visibility.PUBLIC,
        )
        unrelated.skills.set([self.skill])

        self.client.force_authenticate(user=self.sender)

        sender_response = self.client.get(f"{self.kudos_url}?q={self.sender.email}")
        sender_ids = [item["id"] for item in sender_response.data["results"]]

        recipient_response = self.client.get(f"{self.kudos_url}?q={self.recipient.email}")
        recipient_ids = [item["id"] for item in recipient_response.data["results"]]

        self.assertEqual(sender_response.status_code, status.HTTP_200_OK)
        self.assertIn(sender_match.id, sender_ids)
        self.assertNotIn(unrelated.id, sender_ids)

        self.assertEqual(recipient_response.status_code, status.HTTP_200_OK)
        self.assertIn(sender_match.id, recipient_ids)
        self.assertIn(recipient_match.id, recipient_ids)
        self.assertNotIn(unrelated.id, recipient_ids)

    def test_home_search_sender_and_recipient_text_filters_match_users(self):
        """Verify sender/recipient query params accept user text values as filters."""
        matching = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Match both people filters",
            visibility=Kudos.Visibility.PUBLIC,
        )
        matching.skills.set([self.skill])
        sender_only = Kudos.objects.create(
            sender=self.sender,
            recipient=self.staff,
            message="Match sender only",
            visibility=Kudos.Visibility.PUBLIC,
        )
        sender_only.skills.set([self.skill])
        unrelated = Kudos.objects.create(
            sender=self.viewer,
            recipient=self.staff,
            message="Match neither filter",
            visibility=Kudos.Visibility.PUBLIC,
        )
        unrelated.skills.set([self.skill])

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(
            f"{self.kudos_url}?sender={self.sender.email}&recipient={self.recipient.email}"
        )
        result_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(matching.id, result_ids)
        self.assertNotIn(sender_only.id, result_ids)
        self.assertNotIn(unrelated.id, result_ids)

    def test_recipient_filter_matches_secondary_recipient(self):
        """Verify recipient filtering includes non-primary recipients on a kudos item."""
        matching = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Two recipients on one kudos",
            visibility=Kudos.Visibility.PUBLIC,
        )
        matching.recipients.set([self.recipient, self.viewer])
        matching.skills.set([self.skill])

        unrelated = Kudos.objects.create(
            sender=self.sender,
            recipient=self.staff,
            message="Single unrelated recipient",
            visibility=Kudos.Visibility.PUBLIC,
        )
        unrelated.skills.set([self.skill])

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(f"{self.kudos_url}?recipient={self.viewer.id}")
        result_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(matching.id, result_ids)
        self.assertNotIn(unrelated.id, result_ids)

    def test_home_search_query_matches_profile_display_name(self):
        """Verify general home search matches sender/recipient profile display names."""
        Profile.objects.create(user=self.recipient, display_name="Bridget Tang")

        matching = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Profile-based search result",
            visibility=Kudos.Visibility.PUBLIC,
        )
        matching.skills.set([self.skill])
        unrelated = Kudos.objects.create(
            sender=self.viewer,
            recipient=self.staff,
            message="No profile match here",
            visibility=Kudos.Visibility.PUBLIC,
        )
        unrelated.skills.set([self.skill])

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(f"{self.kudos_url}?q=Bridget")
        result_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(matching.id, result_ids)
        self.assertNotIn(unrelated.id, result_ids)

    def test_admin_can_view_private_kudos_but_non_member_cannot(self):
        """Verify visibility rules for private kudos between staff and non-members.

        Expected behavior:
            - unrelated non-staff user cannot see private kudos in list feed
            - staff user can see private kudos in list feed
        """
        private_kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Private kudos",
            visibility=Kudos.Visibility.PRIVATE,
        )
        private_kudos.skills.set([self.skill])

        self.client.force_authenticate(user=self.viewer)
        viewer_response = self.client.get(self.kudos_url)
        viewer_ids = [item["id"] for item in viewer_response.data["results"]]

        self.client.force_authenticate(user=self.staff)
        staff_response = self.client.get(self.kudos_url)
        staff_ids = [item["id"] for item in staff_response.data["results"]]

        self.assertEqual(viewer_response.status_code, status.HTTP_200_OK)
        self.assertEqual(staff_response.status_code, status.HTTP_200_OK)
        self.assertNotIn(private_kudos.id, viewer_ids)
        self.assertIn(private_kudos.id, staff_ids)

    def test_admin_can_approve_archive_unarchive_kudos(self):
        """Verify staff moderation actions mutate approval/archive audit fields.

        Expected behavior:
            - approve sets `is_approved` and `approved_by`
            - archive sets `is_archived` and `archived_by`
            - unarchive clears archive flags/metadata
        """
        kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Moderate me",
            visibility=Kudos.Visibility.PUBLIC,
        )
        kudos.skills.set([self.skill])

        self.client.force_authenticate(user=self.staff)
        approve_resp = self.client.post(f"{self.kudos_url}{kudos.id}/approve/")
        archive_resp = self.client.post(f"{self.kudos_url}{kudos.id}/archive/")
        unarchive_resp = self.client.post(f"{self.kudos_url}{kudos.id}/unarchive/")

        self.assertEqual(approve_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(approve_resp.data["is_approved"])
        self.assertEqual(approve_resp.data["approved_by"]["id"], self.staff.id)

        self.assertEqual(archive_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(archive_resp.data["is_archived"])
        self.assertEqual(archive_resp.data["archived_by"]["id"], self.staff.id)

        self.assertEqual(unarchive_resp.status_code, status.HTTP_200_OK)
        self.assertFalse(unarchive_resp.data["is_archived"])
        self.assertIsNone(unarchive_resp.data["archived_by"])

    def test_archived_kudos_hidden_from_non_admin_feeds(self):
        """Verify archived kudos are hidden from non-admin private/public feeds.

        Expected behavior:
            - archived item absent from authenticated non-admin feed
            - archived item absent from public feed
        """
        kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Archive visibility",
            visibility=Kudos.Visibility.PUBLIC,
        )
        kudos.skills.set([self.skill])

        self.client.force_authenticate(user=self.staff)
        self.client.post(f"{self.kudos_url}{kudos.id}/archive/")

        self.client.force_authenticate(user=self.viewer)
        private_feed = self.client.get(self.kudos_url)
        public_feed = self.client.get("/api/kudos/public/")

        private_ids = [item["id"] for item in private_feed.data["results"]]
        public_ids = [item["id"] for item in public_feed.data["results"]]

        self.assertNotIn(kudos.id, private_ids)
        self.assertNotIn(kudos.id, public_ids)

    def test_non_admin_cannot_approve_archive_or_export(self):
        """Verify non-staff users are blocked from admin moderation/export actions.

        Expected behavior:
            - approve endpoint returns 403
            - archive endpoint returns 403
            - export endpoint returns 403
        """
        kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Unauthorized moderation",
            visibility=Kudos.Visibility.PUBLIC,
        )
        kudos.skills.set([self.skill])

        self.client.force_authenticate(user=self.sender)
        approve_resp = self.client.post(f"{self.kudos_url}{kudos.id}/approve/")
        archive_resp = self.client.post(f"{self.kudos_url}{kudos.id}/archive/")
        export_resp = self.client.get(f"{self.kudos_url}export/")

        self.assertEqual(approve_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(archive_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(export_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_export_returns_csv(self):
        """Verify staff export endpoint returns CSV with expected header and row data.

        Expected behavior:
            - response is 200 with `text/csv` content type
            - CSV header includes core kudos columns
            - exported data includes created kudos message
        """
        kudos = Kudos.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message="Export me",
            visibility=Kudos.Visibility.PUBLIC,
        )
        kudos.skills.set([self.skill])

        self.client.force_authenticate(user=self.staff)
        response = self.client.get(f"{self.kudos_url}export/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", response["Content-Type"])
        content = response.content.decode("utf-8")
        self.assertIn("id,sender,recipients,message", content.splitlines()[0])
        self.assertIn("Export me", content)
