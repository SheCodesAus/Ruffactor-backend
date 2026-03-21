release: python manage.py upgrade_legacy_auth_schema && python manage.py migrate
web: gunicorn ruffactor_backend.wsgi --log-file -
