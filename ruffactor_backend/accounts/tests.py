from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Kudos, SkillCategory


User = get_user_model()


class UserAccountViewTests(APITestCase):
    def setUp(self):
        """Prepare shared fixtures for user-account endpoint tests.

        This creates one authenticated user and stores the `/auth/user/` URL used
        by PATCH and DELETE test scenarios.
        """
        self.user = User.objects.create_user(
            username="patch_delete_user",
            email="patch_delete_user@example.com",
            password="StrongPass123!",
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
        recipient = User.objects.create_user(
            username="patch_delete_recipient",
            email="patch_delete_recipient@example.com",
            password="StrongPass123!",
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


class KudosApiTicketTests(APITestCase):
    def setUp(self):
        """Prepare shared fixtures for kudos API ticket coverage.

        This creates sender/recipient/viewer/staff users, active and inactive skills,
        and stores the base `/api/kudos/` endpoint URL.
        """
        self.sender = User.objects.create_user(
            username="kudos_sender",
            email="kudos_sender@example.com",
            password="StrongPass123!",
        )
        self.recipient = User.objects.create_user(
            username="kudos_recipient",
            email="kudos_recipient@example.com",
            password="StrongPass123!",
        )
        self.viewer = User.objects.create_user(
            username="kudos_viewer",
            email="kudos_viewer@example.com",
            password="StrongPass123!",
        )
        self.staff = User.objects.create_user(
            username="kudos_staff",
            email="kudos_staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.skill = SkillCategory.objects.create(
            name="Teamwork",
            slug="teamwork",
            is_active=True,
        )
        self.inactive_skill = SkillCategory.objects.create(
            name="Legacy",
            slug="legacy",
            is_active=False,
        )
        self.kudos_url = "/api/kudos/"

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
        self.assertIn("id,sender,recipient,message", content.splitlines()[0])
        self.assertIn("Export me", content)
