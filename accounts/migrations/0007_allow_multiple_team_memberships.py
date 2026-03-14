from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_seed_default_teams_and_enforce_single_membership"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="teammembership",
            name="uniq_user_team_membership",
        ),
    ]
