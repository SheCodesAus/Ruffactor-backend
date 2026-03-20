from django.apps import AppConfig
from django.core.checks import Error, Tags, register
from django.db import connections
from django.db.utils import OperationalError, ProgrammingError


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'


@register(Tags.database)
def check_custom_user_schema_compatibility(app_configs, **kwargs):
    """Detect legacy databases that still only have Django's old auth_user table."""
    errors = []
    database_aliases = kwargs.get("databases")
    if database_aliases is None:
        database_aliases = list(connections)

    for alias in database_aliases:
        try:
            tables = set(connections[alias].introspection.table_names())
        except (OperationalError, ProgrammingError):
            continue

        if "auth_user" in tables and "accounts_user" not in tables:
            errors.append(
                Error(
                    "Legacy auth_user schema detected for the accounts app.",
                    hint=(
                        "This backend now uses accounts.User as AUTH_USER_MODEL. "
                        "Run `python manage.py upgrade_legacy_auth_schema` to bootstrap "
                        "accounts_user from the old auth_user table before deploying this version."
                    ),
                    id="accounts.E001",
                    obj=f"database:{alias}",
                )
            )
    return errors
