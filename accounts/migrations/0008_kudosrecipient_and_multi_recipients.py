import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_kudos_recipients(apps, schema_editor):
    Kudos = apps.get_model("accounts", "Kudos")
    KudosRecipient = apps.get_model("accounts", "KudosRecipient")

    recipient_links = [
        KudosRecipient(kudos_id=kudos.id, user_id=kudos.recipient_id)
        for kudos in Kudos.objects.exclude(recipient_id__isnull=True)
    ]
    KudosRecipient.objects.bulk_create(recipient_links, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_allow_multiple_team_memberships"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="KudosRecipient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kudos",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recipient_links",
                        to="accounts.kudos",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="kudos_recipient_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="kudos",
            name="recipients",
            field=models.ManyToManyField(
                blank=True,
                related_name="kudos_received_multi",
                through="accounts.KudosRecipient",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="kudosrecipient",
            index=models.Index(fields=["user", "created_at"], name="accounts_ku_user_id_f2a198_idx"),
        ),
        migrations.AddIndex(
            model_name="kudosrecipient",
            index=models.Index(fields=["kudos", "created_at"], name="accounts_ku_kudos_i_6d23ab_idx"),
        ),
        migrations.AddConstraint(
            model_name="kudosrecipient",
            constraint=models.UniqueConstraint(fields=("kudos", "user"), name="uniq_kudos_recipient"),
        ),
        migrations.RunPython(
            backfill_kudos_recipients,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
