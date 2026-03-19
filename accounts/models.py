from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import DEFAULT_DB_ALIAS, connections
from django.db import models
from django.db.models import F, Q
from django.db.utils import OperationalError, ProgrammingError


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The email field must be set.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or DEFAULT_DB_ALIAS
        super().save(*args, **kwargs)
        _sync_legacy_auth_user_row(self, using=using)

    def delete(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or DEFAULT_DB_ALIAS
        user_id = self.pk
        result = super().delete(*args, **kwargs)
        _delete_legacy_auth_user_row(user_id, using=using)
        return result

    def __str__(self):
        return _user_label(self)


def _user_label(user):
    """Return a human-readable label for a user without relying on login fields."""
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or user.email


def _legacy_auth_user_table_exists(using=DEFAULT_DB_ALIAS):
    connection = connections[using]
    try:
        return "auth_user" in connection.introspection.table_names()
    except (OperationalError, ProgrammingError):
        return False


def _sync_legacy_auth_user_row(user, using=DEFAULT_DB_ALIAS):
    """Mirror the custom user row into a legacy auth_user table when it still exists."""
    if user.pk is None or not _legacy_auth_user_table_exists(using):
        return

    with connections[using].cursor() as cursor:
        cursor.execute("SELECT 1 FROM auth_user WHERE id = %s", [user.pk])
        row_exists = cursor.fetchone() is not None
        values = [
            user.password,
            user.last_login,
            user.is_superuser,
            user.email,
            user.last_name,
            user.email,
            user.is_staff,
            user.is_active,
            user.date_joined,
            user.first_name,
        ]
        if row_exists:
            cursor.execute(
                """
                UPDATE auth_user
                SET password = %s,
                    last_login = %s,
                    is_superuser = %s,
                    username = %s,
                    last_name = %s,
                    email = %s,
                    is_staff = %s,
                    is_active = %s,
                    date_joined = %s,
                    first_name = %s
                WHERE id = %s
                """,
                [*values, user.pk],
            )
        else:
            cursor.execute(
                """
                INSERT INTO auth_user (
                    id,
                    password,
                    last_login,
                    is_superuser,
                    username,
                    last_name,
                    email,
                    is_staff,
                    is_active,
                    date_joined,
                    first_name
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [user.pk, *values],
            )


def _delete_legacy_auth_user_row(user_id, using=DEFAULT_DB_ALIAS):
    """Delete the mirrored legacy auth_user row when it exists."""
    if not user_id or not _legacy_auth_user_table_exists(using):
        return

    with connections[using].cursor() as cursor:
        cursor.execute("DELETE FROM auth_user WHERE id = %s", [user_id])


class Profile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(blank=True)
    active_team = models.ForeignKey(
        "Team",
        on_delete=models.SET_NULL,
        related_name="active_profiles",
        null=True,
        blank=True,
    )

    def __str__(self):
        """Return a display-friendly profile label.

        Returns:
            str: `display_name` when provided, otherwise the linked name/email.
        """
        return self.display_name or _user_label(self.user)


class SkillCategory(TimeStampedModel):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        """Return the skill display value used in admin and API debug output.

        Returns:
            str: Skill name.
        """
        return self.name


class Team(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        """Return the team display value used in admin and API debug output.

        Returns:
            str: Team name.
        """
        return self.name


class TeamMembership(TimeStampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships",
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["team", "user"], name="uniq_team_member"),
        ]
        indexes = [
            models.Index(fields=["team", "role"]),
            models.Index(fields=["user", "role"]),
        ]

    def __str__(self):
        """Return a concise membership description.

        Returns:
            str: Formatted string including user, team, and membership role.
        """
        return f"{_user_label(self.user)} in {self.team} ({self.role})"


class Event(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["starts_at", "name"]

    def __str__(self):
        """Return the event name for admin and API debug output."""
        return self.name


class Collection(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    kudos = models.ManyToManyField("Kudos", related_name="collections", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        """Return the collection name for admin and API debug output."""
        return self.name


class Kudos(TimeStampedModel):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        TEAM = "team", "Team"
        PRIVATE = "private", "Private"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kudos_sent",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kudos_received",
    )
    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="KudosRecipient",
        related_name="kudos_received_multi",
        blank=True,
    )
    message = models.TextField(max_length=1000)
    link_url = models.URLField(blank=True)
    media_url = models.URLField(blank=True)
    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    skills = models.ManyToManyField(
        SkillCategory,
        through="KudosSkillTag",
        related_name="kudos_posts",
    )
    target_teams = models.ManyToManyField(
        Team,
        through="KudosTargetTeam",
        related_name="targeted_kudos",
        blank=True,
    )
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="kudos_approved",
        null=True,
        blank=True,
    )
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="kudos_archived",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(sender=F("recipient")),
                name="kudos_sender_not_recipient",
            ),
        ]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["sender", "-created_at"]),
            models.Index(fields=["visibility", "-created_at"]),
            models.Index(fields=["is_approved", "-created_at"]),
            models.Index(fields=["is_archived", "-created_at"]),
        ]

    def __str__(self):
        """Return a short sender-to-recipient description.

        Returns:
            str: Human-readable sender and recipient summary.
        """
        return f"Kudos from {_user_label(self.sender)} to {_user_label(self.recipient)}"


class KudosTargetTeam(TimeStampedModel):
    kudos = models.ForeignKey(
        Kudos,
        on_delete=models.CASCADE,
        related_name="team_targets",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="kudos_targets",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kudos", "team"], name="uniq_kudos_target_team"),
        ]
        indexes = [
            models.Index(fields=["team", "created_at"]),
            models.Index(fields=["kudos", "created_at"]),
        ]

    def __str__(self):
        """Return compact identifier for a kudos/team relation row.

        Returns:
            str: Composite identifier in the form `{kudos_id}:{team_name}`.
        """
        return f"{self.kudos_id}:{self.team.name}"


class KudosRecipient(TimeStampedModel):
    kudos = models.ForeignKey(
        Kudos,
        on_delete=models.CASCADE,
        related_name="recipient_links",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kudos_recipient_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kudos", "user"], name="uniq_kudos_recipient"),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["kudos", "created_at"]),
        ]

    def __str__(self):
        """Return compact identifier for a kudos/recipient relation row."""
        return f"{self.kudos_id}:{_user_label(self.user)}"


class KudosSkillTag(TimeStampedModel):
    kudos = models.ForeignKey(
        Kudos,
        on_delete=models.CASCADE,
        related_name="skill_tags",
    )
    skill = models.ForeignKey(
        SkillCategory,
        on_delete=models.CASCADE,
        related_name="kudos_tags",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kudos", "skill"], name="uniq_kudos_skill_tag"),
        ]
        indexes = [
            models.Index(fields=["skill", "created_at"]),
            models.Index(fields=["kudos", "created_at"]),
        ]

    def __str__(self):
        """Return compact identifier for a kudos/skill relation row.

        Returns:
            str: Composite identifier in the form `{kudos_id}:{skill_name}`.
        """
        return f"{self.kudos_id}:{self.skill.name}"


class KudosComment(TimeStampedModel):
    kudos = models.ForeignKey(
        Kudos,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kudos_comments",
    )
    body = models.TextField(max_length=1000)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["kudos", "created_at"]),
            models.Index(fields=["author", "created_at"]),
        ]

    def __str__(self):
        """Return compact identifier for a comment and parent kudos relation.

        Returns:
            str: Composite identifier containing comment and kudos IDs.
        """
        return f"Comment {self.id} on Kudos {self.kudos_id}"
