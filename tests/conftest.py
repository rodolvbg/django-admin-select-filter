import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
