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


def normalize_default_skills(apps, schema_editor):
    SkillCategory = apps.get_model("accounts", "SkillCategory")
    for name, slug, description in DEFAULT_SKILLS:
        skill, _ = SkillCategory.objects.get_or_create(
            name=name,
            defaults={
                "slug": slug,
                "description": description,
                "is_active": True,
            },
        )

        updates = []
        if skill.slug != slug:
            skill.slug = slug
            updates.append("slug")
        if skill.description != description:
            skill.description = description
            updates.append("description")
        if not skill.is_active:
            skill.is_active = True
            updates.append("is_active")

        if updates:
            skill.save(update_fields=updates)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_seed_default_skills"),
    ]

    operations = [
        migrations.RunPython(
            normalize_default_skills,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
