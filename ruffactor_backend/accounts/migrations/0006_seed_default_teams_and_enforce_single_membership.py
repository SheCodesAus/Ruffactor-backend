from django.db import migrations, models


DEFAULT_TEAMS = [
    ("Account Management", "account-management", "Account Management team"),
    ("Sales", "sales", "Sales team"),
    ("Tech", "tech", "Tech team"),
    ("Management", "management", "Management team"),
    ("Administration", "administration", "Administration team"),
]


def seed_default_teams(apps, schema_editor):
    Team = apps.get_model("accounts", "Team")
    for name, slug, description in DEFAULT_TEAMS:
        Team.objects.get_or_create(
            name=name,
            defaults={"slug": slug, "description": description},
        )


def collapse_memberships_to_one_team_per_user(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    TeamMembership = apps.get_model("accounts", "TeamMembership")

    user_ids = TeamMembership.objects.values_list("user_id", flat=True).distinct()
    for user_id in user_ids:
        memberships = list(
            TeamMembership.objects.filter(user_id=user_id).order_by("-updated_at", "-created_at", "-id")
        )
        if len(memberships) <= 1:
            continue

        profile = Profile.objects.filter(user_id=user_id).first()
        active_team_id = getattr(profile, "active_team_id", None)
        membership_to_keep = None
        if active_team_id is not None:
            membership_to_keep = next(
                (membership for membership in memberships if membership.team_id == active_team_id),
                None,
            )
        if membership_to_keep is None:
            membership_to_keep = memberships[0]

        TeamMembership.objects.filter(user_id=user_id).exclude(pk=membership_to_keep.pk).delete()
        if profile is not None and profile.active_team_id != membership_to_keep.team_id:
            profile.active_team_id = membership_to_keep.team_id
            profile.save(update_fields=["active_team", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_kudos_approved_at_kudos_approved_by_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_default_teams,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            collapse_memberships_to_one_team_per_user,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="teammembership",
            constraint=models.UniqueConstraint(
                fields=("user",),
                name="uniq_user_team_membership",
            ),
        ),
    ]
