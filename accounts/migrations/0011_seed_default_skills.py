from django.db import migrations


DEFAULT_SKILLS = [
    ("Sales", "sales", "Sales skill"),
    ("Account Management", "account-management", "Account Management skill"),
    ("Lead Generation", "lead-generation", "Lead Generation skill"),
    ("Communication", "communication", "Communication skill"),
    ("Project Management", "project-management", "Project Management skill"),
    ("Business Administration", "business-administration", "Business Administration skill"),
    ("Reporting", "reporting", "Reporting skill"),
    ("Website Development", "website-development", "Website Development skill"),
]


def seed_default_skills(apps, schema_editor):
    SkillCategory = apps.get_model("accounts", "SkillCategory")
    for name, slug, description in DEFAULT_SKILLS:
        SkillCategory.objects.get_or_create(
            name=name,
            defaults={
                "slug": slug,
                "description": description,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_alter_user_options_alter_user_managers_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_default_skills,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
