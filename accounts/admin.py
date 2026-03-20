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
        "first_name",
        "last_name",
        "email",
        "is_staff",
        "is_active",
        "date_joined",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("first_name", "last_name", "email")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )


admin.site.site_header = "Ruffactor Admin Dashboard"
admin.site.site_title = "Ruffactor Admin"
admin.site.index_title = "Administration"


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ("team", "user_label", "role", "created_at")
    list_filter = ("role", "team")
    search_fields = ("team__name", "user__email", "user__first_name", "user__last_name")

    def user_label(self, obj):
        return " ".join(part for part in [obj.user.first_name, obj.user.last_name] if part).strip() or obj.user.email

    user_label.short_description = "User"


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
    list_display = ("user_label", "display_name", "active_team", "created_at")
    list_filter = ("active_team",)
    search_fields = ("user__email", "user__first_name", "user__last_name", "display_name")

    def user_label(self, obj):
        return " ".join(part for part in [obj.user.first_name, obj.user.last_name] if part).strip() or obj.user.email

    user_label.short_description = "User"


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(Kudos)
class KudosAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sender_label",
        "recipient_list",
        "visibility",
        "is_approved",
        "is_archived",
        "created_at",
    )
    list_filter = ("visibility", "is_approved", "is_archived")
    search_fields = (
        "message",
        "sender__email",
        "sender__first_name",
        "sender__last_name",
        "recipient__email",
        "recipient__first_name",
        "recipient__last_name",
        "recipients__email",
        "recipients__first_name",
        "recipients__last_name",
    )

    def sender_label(self, obj):
        return " ".join(part for part in [obj.sender.first_name, obj.sender.last_name] if part).strip() or obj.sender.email

    sender_label.short_description = "Sender"

    def recipient_list(self, obj):
        recipients = [
            " ".join(part for part in [user.first_name, user.last_name] if part).strip() or user.email
            for user in obj.recipients.all()
        ]
        if recipients:
            return ", ".join(recipients)
        if obj.recipient_id:
            return " ".join(
                part for part in [obj.recipient.first_name, obj.recipient.last_name] if part
            ).strip() or obj.recipient.email
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
    list_display = ("kudos", "user_label", "created_at")
    list_filter = ("created_at",)
    search_fields = ("kudos__message", "user__email", "user__first_name", "user__last_name")

    def user_label(self, obj):
        return " ".join(part for part in [obj.user.first_name, obj.user.last_name] if part).strip() or obj.user.email

    user_label.short_description = "User"


@admin.register(KudosComment)
class KudosCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "kudos", "author_label", "created_at")
    search_fields = ("body", "author__email", "author__first_name", "author__last_name", "kudos__message")
    list_filter = ("created_at",)

    def author_label(self, obj):
        return " ".join(part for part in [obj.author.first_name, obj.author.last_name] if part).strip() or obj.author.email

    author_label.short_description = "Author"
