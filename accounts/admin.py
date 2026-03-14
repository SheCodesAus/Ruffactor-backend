from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Collection,
    Event,
    Kudos,
    KudosComment,
    KudosRecipient,
    KudosSkillTag,
    KudosTargetTeam,
    Profile,
    SkillCategory,
    Team,
    TeamMembership,
)

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    fk_name = "user"


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = (ProfileInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "date_joined",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)


admin.site.site_header = "Ruffactor Admin Dashboard"
admin.site.site_title = "Ruffactor Admin"
admin.site.index_title = "Administration"


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ("team", "user", "role", "created_at")
    list_filter = ("role", "team")
    search_fields = ("team__name", "user__username", "user__email")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "starts_at", "ends_at", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    filter_horizontal = ("kudos",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "active_team", "created_at")
    list_filter = ("active_team",)
    search_fields = ("user__username", "user__email", "display_name")


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(Kudos)
class KudosAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sender",
        "recipient_list",
        "visibility",
        "is_approved",
        "is_archived",
        "created_at",
    )
    list_filter = ("visibility", "is_approved", "is_archived")
    search_fields = ("message", "sender__username", "recipient__username", "recipients__username")

    def recipient_list(self, obj):
        recipients = list(obj.recipients.values_list("username", flat=True))
        if recipients:
            return ", ".join(recipients)
        if obj.recipient_id:
            return obj.recipient.username
        return ""

    recipient_list.short_description = "Recipients"


@admin.register(KudosTargetTeam)
class KudosTargetTeamAdmin(admin.ModelAdmin):
    list_display = ("kudos", "team", "created_at")
    list_filter = ("team",)
    search_fields = ("kudos__message", "team__name")


@admin.register(KudosSkillTag)
class KudosSkillTagAdmin(admin.ModelAdmin):
    list_display = ("kudos", "skill", "created_at")
    list_filter = ("skill",)
    search_fields = ("kudos__message", "skill__name")


@admin.register(KudosRecipient)
class KudosRecipientAdmin(admin.ModelAdmin):
    list_display = ("kudos", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("kudos__message", "user__username", "user__email")


@admin.register(KudosComment)
class KudosCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "kudos", "author", "created_at")
    search_fields = ("body", "author__username", "kudos__message")
    list_filter = ("created_at",)
