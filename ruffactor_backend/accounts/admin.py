from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Kudos,
    KudosComment,
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
        "recipient",
        "visibility",
        "is_approved",
        "is_archived",
        "created_at",
    )
    list_filter = ("visibility", "is_approved", "is_archived")
    search_fields = ("message", "sender__username", "recipient__username")


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


@admin.register(KudosComment)
class KudosCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "kudos", "author", "created_at")
    search_fields = ("body", "author__username", "kudos__message")
    list_filter = ("created_at",)
