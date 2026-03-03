from django.conf import settings
from django.db import models
from django.db.models import F, Q


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Profile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(blank=True)

    def __str__(self):
        return self.display_name or self.user.get_username()


class SkillCategory(TimeStampedModel):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Kudos(TimeStampedModel):
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
    message = models.TextField(max_length=1000)
    link_url = models.URLField(blank=True)
    media_url = models.URLField(blank=True)
    is_public = models.BooleanField(default=True)
    skills = models.ManyToManyField(
        SkillCategory,
        through="KudosSkillTag",
        related_name="kudos_posts",
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
        ]

    def __str__(self):
        return f"Kudos from {self.sender} to {self.recipient}"


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
        return f"{self.kudos_id}:{self.skill.name}"
