"""Minimal Django settings so django-stubs' mypy plugin can boot standalone.

Not used at runtime; only ``tool.django-stubs.django_settings_module`` points
here. Kept to only stdlib Django apps so the mypy pre-commit hook (which
type-checks this package in isolation, without installing it) can import it.
"""

SECRET_KEY = "mypy"
USE_TZ = True
DATABASES: dict[str, dict[str, str]] = {}
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
]
