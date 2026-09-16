import os

import django_stubs_ext

# pytest-playwright's sync API leaves a background asyncio loop running in
# this thread, which trips Django's async-safety guard during the one-time
# test database setup (a plain sqlite DDL call, not actually unsafe here).
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

# Lets test code subscript generics like ModelAdmin[Book] at runtime, since
# this settings module also backs the mypy pre-commit hook's type-checking
# pass over tests/.
django_stubs_ext.monkeypatch()

SECRET_KEY = "test-secret-key"
DEBUG = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_admin_select_filter",
    "tests.testapp",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

STATIC_URL = "/static/"
