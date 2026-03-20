import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("first_name", models.CharField(max_length=150)),
                ("last_name", models.CharField(max_length=150)),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SkillCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80, unique=True)),
                ("slug", models.SlugField(max_length=90, unique=True)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Kudos",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("message", models.TextField(max_length=1000)),
                ("link_url", models.URLField(blank=True)),
                ("media_url", models.URLField(blank=True)),
                ("is_public", models.BooleanField(default=True)),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="kudos_received",
                        to="accounts.user",
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="kudos_sent",
                        to="accounts.user",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("display_name", models.CharField(blank=True, max_length=120)),
                ("bio", models.TextField(blank=True)),
                ("avatar_url", models.URLField(blank=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to="accounts.user",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="KudosSkillTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kudos",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_tags",
                        to="accounts.kudos",
                    ),
                ),
                (
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="kudos_tags",
                        to="accounts.skillcategory",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="kudos",
            name="skills",
            field=models.ManyToManyField(
                related_name="kudos_posts",
                through="accounts.KudosSkillTag",
                to="accounts.skillcategory",
            ),
        ),
        migrations.AddIndex(
            model_name="kudosskilltag",
            index=models.Index(fields=["skill", "created_at"], name="accounts_ku_skill_i_f6257e_idx"),
        ),
        migrations.AddIndex(
            model_name="kudosskilltag",
            index=models.Index(fields=["kudos", "created_at"], name="accounts_ku_kudos_i_9a33f3_idx"),
        ),
        migrations.AddConstraint(
            model_name="kudosskilltag",
            constraint=models.UniqueConstraint(fields=("kudos", "skill"), name="uniq_kudos_skill_tag"),
        ),
        migrations.AddIndex(
            model_name="kudos",
            index=models.Index(fields=["-created_at"], name="accounts_ku_created_1ae97f_idx"),
        ),
        migrations.AddIndex(
            model_name="kudos",
            index=models.Index(fields=["recipient", "-created_at"], name="accounts_ku_recipie_15d229_idx"),
        ),
        migrations.AddIndex(
            model_name="kudos",
            index=models.Index(fields=["sender", "-created_at"], name="accounts_ku_sender__5b4f01_idx"),
        ),
        migrations.AddConstraint(
            model_name="kudos",
            constraint=models.CheckConstraint(
                condition=models.Q(("sender", models.F("recipient")), _negated=True),
                name="kudos_sender_not_recipient",
            ),
        ),
    ]
