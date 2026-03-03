from django.contrib import admin

from .models import Kudos, KudosSkillTag, Profile, SkillCategory


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "created_at")
    search_fields = ("user__username", "user__email", "display_name")


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(Kudos)
class KudosAdmin(admin.ModelAdmin):
    list_display = ("id", "sender", "recipient", "is_public", "created_at")
    list_filter = ("is_public",)
    search_fields = ("message", "sender__username", "recipient__username")


@admin.register(KudosSkillTag)
class KudosSkillTagAdmin(admin.ModelAdmin):
    list_display = ("kudos", "skill", "created_at")
    list_filter = ("skill",)
    search_fields = ("kudos__message", "skill__name")
