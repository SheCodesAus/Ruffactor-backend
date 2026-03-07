from django.contrib import admin

from .models import (
    Kudos,
    KudosSkillTag,
    KudosTargetTeam,
    Profile,
    SkillCategory,
    Team,
    TeamMembership,
)


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
    list_display = ("id", "sender", "recipient", "visibility", "created_at")
    list_filter = ("visibility",)
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
