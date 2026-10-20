"""Django's own Content Security Policy middleware (6.0+): the filters'
scripts carry the request's nonce, the same the policy header sends."""

import re

import django
import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from tests.settings import MIDDLEWARE

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(django.VERSION < (6, 0), reason="Django 6.0+ middleware"),
]


class TestContentSecurityPolicy:
    """Script nonces follow Django's CSP middleware."""

    def test_scripts_carry_the_policy_nonce(self):
        from django.utils.csp import CSP

        User.objects.create_superuser("admin", "admin@example.com", "password")
        with override_settings(
            MIDDLEWARE=[
                *MIDDLEWARE,
                "django.middleware.csp.ContentSecurityPolicyMiddleware",
            ],
            SECURE_CSP={"default-src": [CSP.SELF], "script-src": [CSP.NONCE]},
        ):
            client = Client()
            client.login(username="admin", password="password")
            response = client.get("/admin/testapp/book/")

        header = response.headers["Content-Security-Policy"]
        match = re.search(r"'nonce-([^']+)'", header)
        assert match
        policy_nonce = match.group(1)
        content = response.content.decode()
        scripts = re.findall(
            r'<script type="module" nonce="([^"]+)" src="[^"]*admin_select_filter/js/',
            content,
        )
        assert scripts
        assert set(scripts) == {policy_nonce}
        assert "importmap" not in content
