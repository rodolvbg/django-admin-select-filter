"""Django's own Content Security Policy middleware (6.0+): the filters'
scripts carry the request's nonce, the same the policy header sends."""

import re
from unittest import skipIf

import django
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from tests.settings import MIDDLEWARE


@skipIf(django.VERSION < (6, 0), "Django 6.0+ middleware")
class TestContentSecurityPolicy(TestCase):
    """Script nonces follow Django's CSP middleware."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_scripts_carry_the_policy_nonce(self):
        from django.utils.csp import CSP

        with override_settings(
            MIDDLEWARE=[
                *MIDDLEWARE,
                "django.middleware.csp.ContentSecurityPolicyMiddleware",
            ],
            SECURE_CSP={"default-src": [CSP.SELF], "script-src": [CSP.NONCE]},
        ):
            response = self.client.get("/admin/testapp/book/")

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
