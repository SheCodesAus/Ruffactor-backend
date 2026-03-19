from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, router, transaction


class Command(BaseCommand):
    help = "Bootstrap accounts_user from a legacy auth_user schema without resetting the database."
    requires_system_checks = []

    def handle(self, *args, **options):
        User = get_user_model()
        using = router.db_for_write(User)
        connection = connections[using]
        tables = set(connection.introspection.table_names())

        if "accounts_user" in tables:
            self.stdout.write(self.style.SUCCESS("accounts_user already exists. Nothing to do."))
            return

        if "auth_user" not in tables:
            raise CommandError("No legacy auth_user table was found in this database.")

        user_group_through = User.groups.through._meta.db_table
        user_permission_through = User.user_permissions.through._meta.db_table

        user_columns = [field.column for field in User._meta.local_concrete_fields]
        joined_user_columns = ", ".join(user_columns)

        with transaction.atomic(using=using):
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(User)

            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO accounts_user ({joined_user_columns})
                    SELECT {joined_user_columns}
                    FROM auth_user
                    """
                )

                if "auth_user_groups" in tables:
                    cursor.execute(
                        f"""
                        INSERT INTO {user_group_through} (user_id, group_id)
                        SELECT user_id, group_id
                        FROM auth_user_groups
                        """
                    )

                if "auth_user_user_permissions" in tables:
                    cursor.execute(
                        f"""
                        INSERT INTO {user_permission_through} (user_id, permission_id)
                        SELECT user_id, permission_id
                        FROM auth_user_user_permissions
                        """
                    )

        self.stdout.write(
            self.style.SUCCESS(
                "Legacy auth_user data copied into accounts_user. "
                "Run `python manage.py migrate` next to finish applying project migrations."
            )
        )
