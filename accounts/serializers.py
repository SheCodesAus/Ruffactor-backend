from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from .models import Kudos, KudosComment, Profile, SkillCategory, Team, TeamMembership


User = get_user_model()
PIXEL_PULSE_EMAIL_SUFFIX = getattr(settings, "PIXEL_PULSE_EMAIL_SUFFIX", "+pp@gmail.com").lower()
MAX_KUDOS_RECIPIENTS = 5
MAX_KUDOS_SKILLS = 5


def _normalize_pixel_pulse_email(email):
    """Normalize email input and enforce the allowed Pixel Pulse signup suffix."""
    normalized = email.strip().lower()
    if not normalized.endswith(PIXEL_PULSE_EMAIL_SUFFIX):
        raise serializers.ValidationError(
            "Please use your validated email ending with +pp@gmail.com."
        )
    return normalized

class SignUpSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True, allow_blank=False, max_length=150)
    last_name = serializers.CharField(required=True, allow_blank=False, max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "team_id",
            "password",
            "confirm_password",
        )
        read_only_fields = ("id",)

    def validate_email(self, value):
        """Normalize signup email and enforce uniqueness.

        Args:
            value (str): Raw email submitted by the client.

        Returns:
            str: Lower-cased, trimmed email.

        Raises:
            serializers.ValidationError: If another user already uses this email.
        """
        normalized = _normalize_pixel_pulse_email(value)

        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate(self, attrs):
        """Validate signup password confirmation and password strength.

        Args:
            attrs (dict): Incoming serializer payload.

        Returns:
            dict: Validated payload.

        Raises:
            serializers.ValidationError: If passwords mismatch or fail Django validators.
        """
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        temp_user = User(
            email=attrs.get("email"),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        password_validation.validate_password(attrs["password"], user=temp_user)
        return attrs

    def create(self, validated_data):
        """Create a new user, team membership, and profile row.

        Args:
            validated_data (dict): Validated signup fields.

        Returns:
            User: Newly created user instance with hashed password.
        """
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        team = validated_data.pop("team", None)
        with transaction.atomic():
            user = User.objects.create_user(
                password=password,
                is_active=True,
                **validated_data,
            )
            if team is not None:
                profile, _ = Profile.objects.get_or_create(user=user)
                profile.active_team = team
                profile.save(update_fields=["active_team", "updated_at"])
                TeamMembership.objects.get_or_create(
                    user=user,
                    team=team,
                    defaults={"role": TeamMembership.Role.MEMBER},
                )
        return user


# Forgot password
def _normalize_email(email):
    return email.strip().lower()

def _get_email_candidates(email):
    email = _normalize_email(email)

    if not email.endswith("@gmail.com"):
        return [email]

    local, domain = email.split("@")

    if "+" in local:
        base = local.split("+")[0]
        return [
            email,
            f"{base}@{domain}",
            f"{base}+pp@{domain}",
        ]

    return [
        email,
        f"{local}+pp@{domain}",
    ]

class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return _normalize_email(value)


class ResetPasswordConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError({"uid": "Invalid reset link."})

        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Invalid or expired reset link."})

        password_validation.validate_password(attrs["password"], user=user)

        attrs["user"] = user
        return attrs
    

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        """Authenticate login credentials and validate optional team selection.

        Args:
            attrs (dict): Incoming login payload.

        Returns:
            dict: Payload including authenticated `user` and optional `team`.

        Raises:
            serializers.ValidationError: If credentials fail or selected team is invalid.
        """
        email = attrs.get("email").strip().lower()
        password = attrs.get("password")

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.check_password(password) or not user.is_active:
            raise serializers.ValidationError("Invalid email or password.")

        selected_team = attrs.get("team")
        if selected_team is not None:
            is_member = TeamMembership.objects.filter(user=user, team=selected_team).exists()
            if not is_member:
                raise serializers.ValidationError(
                    {"team_id": "You can only select teams you belong to."}
                )

        attrs["user"] = user
        return attrs

class UserAccountPatchSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    password = serializers.CharField(write_only=True, min_length=8, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        required=False,
        allow_null=True,
    )

    def validate_email(self, value):
        """Normalize email and prevent collisions with other user records.

        Args:
            value (str): Raw email from PATCH payload.

        Returns:
            str: Lower-cased, trimmed email.

        Raises:
            serializers.ValidationError: If email already exists on another account.
        """
        normalized = _normalize_pixel_pulse_email(value)
        user = self.instance
        if User.objects.filter(email__iexact=normalized).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate(self, attrs):
        """Validate user PATCH payload including password and active-team rules.

        Args:
            attrs (dict): Partial update payload.

        Returns:
            dict: Validated update payload.

        Raises:
            serializers.ValidationError: If password fields are incomplete, mismatch,
                fail policy validation, or selected team is not a membership team.
        """
        user = self.instance
        password = attrs.get("password")
        confirm_password = attrs.get("confirm_password")

        if password is not None or confirm_password is not None:
            if password is None or confirm_password is None:
                raise serializers.ValidationError(
                    {"confirm_password": "password and confirm_password are both required."}
                )
            if password != confirm_password:
                raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
            temp_user = User(
                email=attrs.get("email", user.email),
                first_name=attrs.get("first_name", user.first_name),
                last_name=attrs.get("last_name", user.last_name),
            )
            password_validation.validate_password(password, user=temp_user)

        selected_team = attrs.get("team")
        if selected_team is not None:
            is_member = TeamMembership.objects.filter(user=user, team=selected_team).exists()
            if not is_member:
                raise serializers.ValidationError(
                    {"team_id": "You can only select teams you belong to."}
                )
        return attrs

    def update(self, instance, validated_data):
        """Apply partial account updates and synchronize profile active team.

        Args:
            instance (User): Current authenticated user.
            validated_data (dict): Validated fields to apply.

        Returns:
            User: Updated user instance.
        """
        team_provided = "team" in validated_data
        team = validated_data.pop("team", None)
        password = validated_data.pop("password", None)
        validated_data.pop("confirm_password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()

        if team_provided:
            profile, _ = Profile.objects.get_or_create(user=instance)
            profile.active_team = team
            profile.save(update_fields=["active_team", "updated_at"])

        return instance


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # fields = ("id", "username", "first_name", "last_name")
        exclude = ("password",)


class TeamSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Team
        fields = ("id", "name", "slug", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def _next_unique_slug(self, base_slug, instance=None):
        """Generate a unique team slug with numeric suffix fallback.

        Args:
            base_slug (str): Slug candidate derived from team name.
            instance (Team | None): Existing instance during updates.

        Returns:
            str: Unique slug safe for persistence.
        """
        slug = base_slug or "team"
        candidate = slug
        index = 2
        queryset = Team.objects.all()
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        while queryset.filter(slug=candidate).exists():
            candidate = f"{slug}-{index}"
            index += 1
        return candidate

    def validate(self, attrs):
        """Ensure team payload has a valid unique slug for create/update.

        Args:
            attrs (dict): Team serializer payload.

        Returns:
            dict: Payload with generated/updated slug when required.
        """
        if self.instance is not None:
            if "slug" in attrs and attrs["slug"] == "":
                name = attrs.get("name", self.instance.name)
                attrs["slug"] = self._next_unique_slug(slugify(name), instance=self.instance)
            elif "name" in attrs and "slug" not in attrs:
                attrs["slug"] = self._next_unique_slug(
                    slugify(attrs["name"]),
                    instance=self.instance,
                )
            return attrs

        name = attrs.get("name", "")
        raw_slug = attrs.get("slug")
        if raw_slug in (None, ""):
            attrs["slug"] = self._next_unique_slug(slugify(name))
        return attrs


class TeamMembershipSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = TeamMembership
        fields = ("id", "user", "role", "created_at")
        read_only_fields = ("id", "created_at")


class TeamMembershipWriteSerializer(serializers.Serializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source="user")
    role = serializers.ChoiceField(
        choices=TeamMembership.Role.choices,
        default=TeamMembership.Role.MEMBER,
    )


class ActiveTeamWriteSerializer(serializers.Serializer):
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        allow_null=True,
    )

    def validate_team(self, value):
        """Validate that selected active team belongs to the authenticated user.

        Args:
            value (Team | None): Team selected by client.

        Returns:
            Team | None: Valid team (or `None` when clearing active team).

        Raises:
            serializers.ValidationError: If user is not a member of the selected team.
        """
        if value is None:
            return value
        user = self.context["request"].user
        is_member = TeamMembership.objects.filter(user=user, team=value).exists()
        if not is_member:
            raise serializers.ValidationError("You can only select teams you belong to.")
        return value


class SkillCategorySerializer(serializers.ModelSerializer):
    slug = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = SkillCategory
        fields = ("id", "name", "slug", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def _next_unique_slug(self, base_slug, instance=None):
        """Generate a unique skill slug with numeric suffix fallback.

        Args:
            base_slug (str): Slug candidate derived from skill name.
            instance (SkillCategory | None): Existing instance during updates.

        Returns:
            str: Unique slug safe for persistence.
        """
        slug = base_slug or "skill"
        candidate = slug
        index = 2
        queryset = SkillCategory.objects.all()
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        while queryset.filter(slug=candidate).exists():
            candidate = f"{slug}-{index}"
            index += 1
        return candidate

    def validate(self, attrs):
        """Ensure skill payload has a valid unique slug for create/update.

        Args:
            attrs (dict): Skill serializer payload.

        Returns:
            dict: Payload with generated/updated slug when required.
        """
        if self.instance is not None:
            if "slug" in attrs and attrs["slug"] == "":
                name = attrs.get("name", self.instance.name)
                attrs["slug"] = self._next_unique_slug(slugify(name), instance=self.instance)
            elif "name" in attrs and "slug" not in attrs:
                attrs["slug"] = self._next_unique_slug(
                    slugify(attrs["name"]),
                    instance=self.instance,
                )
            return attrs

        name = attrs.get("name", "")
        raw_slug = attrs.get("slug")
        if raw_slug in (None, ""):
            attrs["slug"] = self._next_unique_slug(slugify(name))
        return attrs


class KudosReadSerializer(serializers.ModelSerializer):
    sender = UserSummarySerializer(read_only=True)
    recipient = UserSummarySerializer(read_only=True)
    recipients = serializers.SerializerMethodField()
    approved_by = UserSummarySerializer(read_only=True)
    archived_by = UserSummarySerializer(read_only=True)
    skills = SkillCategorySerializer(many=True, read_only=True)
    target_teams = TeamSerializer(many=True, read_only=True)

    def get_recipients(self, obj):
        """Return all recipients, falling back to the legacy single recipient field."""
        recipients = list(obj.recipients.all())
        if recipients:
            return UserSummarySerializer(recipients, many=True).data
        if obj.recipient_id:
            return UserSummarySerializer([obj.recipient], many=True).data
        return []

    class Meta:
        model = Kudos
        fields = (
            "id",
            "sender",
            "recipient",
            "recipients",
            "message",
            "link_url",
            "media_url",
            "visibility",
            "is_approved",
            "approved_at",
            "approved_by",
            "is_archived",
            "archived_at",
            "archived_by",
            "skills",
            "target_teams",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class KudosWriteSerializer(serializers.ModelSerializer):
    recipient = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )
    recipient_ids = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )
    # Frontend sends a list of active predefined skill IDs (required by validation).
    skill_ids = serializers.PrimaryKeyRelatedField(
        queryset=SkillCategory.objects.filter(is_active=True),
        many=True,
        required=False,
        write_only=True,
    )
    # Team tags may be attached to kudos regardless of visibility.
    target_team_ids = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = Kudos
        fields = (
            "id",
            "recipient",
            "recipient_ids",
            "message",
            "link_url",
            "media_url",
            "visibility",
            "skill_ids",
            "target_team_ids",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        """Validate kudos business rules for recipient, tags, and visibility.

        Args:
            attrs (dict): Create/update payload for kudos.

        Returns:
            dict: Validated payload.

        Raises:
            serializers.ValidationError: If required skill tags are missing, team
                visibility requires no teams or non-member tagging is attempted, or
                sender equals recipient.
        """
        request = self.context["request"]
        user = request.user
        instance = self.instance
        # Keep at least one skill tag on both create and update payloads.
        raw_skills = attrs.get("skill_ids")
        if raw_skills is None and instance is not None:
            raw_skills = list(instance.skills.all())
        elif raw_skills is None:
            raw_skills = []

        deduplicated_skills = []
        seen_skill_ids = set()
        for skill in raw_skills:
            if skill.id in seen_skill_ids:
                continue
            deduplicated_skills.append(skill)
            seen_skill_ids.add(skill.id)

        if not deduplicated_skills:
            raise serializers.ValidationError(
                {"skill_ids": "At least one predefined skill tag is required."}
            )
        if len(deduplicated_skills) > MAX_KUDOS_SKILLS:
            raise serializers.ValidationError(
                {"skill_ids": f"You can select up to {MAX_KUDOS_SKILLS} skills per kudos."}
            )
        attrs["resolved_skills"] = deduplicated_skills

        visibility = attrs.get(
            "visibility",
            getattr(instance, "visibility", Kudos.Visibility.PUBLIC),
        )
        teams = attrs.get("target_team_ids")
        if teams is None and instance is not None:
            teams = list(instance.target_teams.all())
        elif teams is None:
            teams = []

        if visibility == Kudos.Visibility.TEAM and not teams:
            raise serializers.ValidationError(
                {"target_team_ids": "Team visibility requires at least one team."}
            )

        if teams and not user.is_staff:
            team_ids = [team.id for team in teams]
            memberships = set(
                TeamMembership.objects.filter(
                    user=user,
                    team_id__in=team_ids,
                ).values_list("team_id", flat=True)
            )
            if memberships != set(team_ids):
                raise serializers.ValidationError(
                    {"target_team_ids": "You must belong to all targeted teams."}
                )

        raw_recipients = attrs.get("recipient_ids")
        if raw_recipients is None and "recipient" in attrs:
            raw_recipients = [attrs["recipient"]]
        elif raw_recipients is None and instance is not None:
            raw_recipients = list(instance.recipients.all())
            if not raw_recipients and getattr(instance, "recipient_id", None):
                raw_recipients = [instance.recipient]

        if not raw_recipients:
            raise serializers.ValidationError(
                {"recipient_ids": "At least one recipient is required."}
            )

        deduplicated_recipients = []
        seen_recipient_ids = set()
        for recipient in raw_recipients:
            if recipient.id in seen_recipient_ids:
                continue
            deduplicated_recipients.append(recipient)
            seen_recipient_ids.add(recipient.id)

        if user in deduplicated_recipients:
            raise serializers.ValidationError(
                {"recipient_ids": "Sender cannot be one of the recipients."}
            )

        if len(deduplicated_recipients) > MAX_KUDOS_RECIPIENTS:
            raise serializers.ValidationError(
                {"recipient_ids": "You can select up to 5 recipients per kudos."}
            )

        attrs["resolved_recipients"] = deduplicated_recipients

        return attrs

    def create(self, validated_data):
        """Create kudos row and set skills/team target relations.

        Args:
            validated_data (dict): Validated kudos fields.

        Returns:
            Kudos: Newly created kudos owned by the authenticated sender.
        """
        recipients = validated_data.pop("resolved_recipients")
        validated_data.pop("recipient_ids", None)
        validated_data.pop("recipient", None)
        skill_ids = validated_data.pop("resolved_skills", [])
        validated_data.pop("skill_ids", None)
        target_team_ids = validated_data.pop("target_team_ids", [])
        kudos = Kudos.objects.create(
            sender=self.context["request"].user,
            recipient=recipients[0],
            **validated_data,
        )
        kudos.recipients.set(recipients)
        kudos.skills.set(skill_ids)
        kudos.target_teams.set(target_team_ids)
        return kudos

    def update(self, instance, validated_data):
        """Update kudos fields and optionally replace relation sets.

        Args:
            instance (Kudos): Existing kudos instance.
            validated_data (dict): Validated update payload.

        Returns:
            Kudos: Updated kudos instance.
        """
        recipients = validated_data.pop("resolved_recipients", None)
        validated_data.pop("recipient_ids", None)
        skill_ids = validated_data.pop("resolved_skills", None)
        validated_data.pop("skill_ids", None)
        target_team_ids = validated_data.pop("target_team_ids", None)
        primary_recipient = validated_data.pop("recipient", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if recipients is not None:
            instance.recipient = recipients[0]
        elif primary_recipient is not None:
            instance.recipient = primary_recipient
        instance.save()

        if recipients is not None:
            instance.recipients.set(recipients)
        if skill_ids is not None:
            instance.skills.set(skill_ids)
        if target_team_ids is not None:
            instance.target_teams.set(target_team_ids)

        return instance


class KudosCommentReadSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)

    class Meta:
        model = KudosComment
        fields = ("id", "kudos", "author", "body", "created_at", "updated_at")
        read_only_fields = fields


class KudosCommentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = KudosComment
        fields = ("body",)
