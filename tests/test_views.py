import json
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from inline_snapshot import snapshot
from inline_snapshot_django import snapshot_queries

from django_admin_select_filter.views import Select2FilterOptionsView
from tests.testapp.admin import AsyncAuthorFilter, AsyncGenreFilter, GenreFilter
from tests.testapp.models import Author, Book, Country

pytestmark = pytest.mark.django_db


class Select2FilterOptionsViewTests:
    def test_options_requires_all_parameters(self):
        client = Client()
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = client.get(url, {"app_label": "testapp", "model_name": "book"})

        assert response.status_code == 400
        assert queries == snapshot([])

    def test_options_404_for_unknown_model(self):
        client = Client()
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = client.get(
                url,
                {
                    "app_label": "doesnotexist",
                    "model_name": "nope",
                    "parameter_name": "x",
                },
            )

        assert response.status_code == 404
        assert queries == snapshot([])

    def test_options_404_for_unregistered_model(self):
        client = Client()
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = client.get(
                url,
                {
                    "app_label": "contenttypes",
                    "model_name": "contenttype",
                    "parameter_name": "x",
                },
            )

        assert response.status_code == 404
        assert queries == snapshot([])

    def test_options_403_for_unprivileged_user(self):
        client = Client()
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = client.get(
                url,
                {
                    "app_label": "testapp",
                    "model_name": "book",
                    "parameter_name": "author",
                },
            )

        assert response.status_code == 403
        assert queries == snapshot([])

    def test_options_404_when_no_matching_filter(self, admin_client):
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = admin_client.get(
                url,
                {"app_label": "testapp", "model_name": "author", "parameter_name": "x"},
            )

        assert response.status_code == 404
        assert queries == snapshot(
            [
                "SELECT ... FROM django_session WHERE ... LIMIT ...",
                "SELECT ... FROM auth_user WHERE ... LIMIT ...",
            ]
        )

    def test_options_404_for_non_async_filter(self, admin_client):
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = admin_client.get(
                url,
                {
                    "app_label": "testapp",
                    "model_name": "book",
                    "parameter_name": "not_a_real_field",
                },
            )

        assert response.status_code == 404
        assert queries == snapshot(
            [
                "SELECT ... FROM django_session WHERE ... LIMIT ...",
                "SELECT ... FROM auth_user WHERE ... LIMIT ...",
            ]
        )

    def test_options_returns_select2_results_for_foreign_key_filter(self, admin_client):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="Harry Potter", author=author)
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = admin_client.get(
                url,
                {
                    "app_label": "testapp",
                    "model_name": "book",
                    "parameter_name": "author",
                    "q": "Rowl",
                    "facets": "true",
                },
            )

        assert response.status_code == 200
        results = response.json()["results"]
        assert results[0] == {"id": "__all__", "text": "All"}
        assert {"id": str(author.pk), "text": "Rowling (1)"} in results
        assert queries == snapshot(
            [
                "SELECT ... FROM django_session WHERE ... LIMIT ...",
                "SELECT ... FROM auth_user WHERE ... LIMIT ...",
                "SELECT ... FROM testapp_author WHERE ... ORDER BY ... ASC",
                "SELECT ... FROM testapp_book WHERE ... LIMIT ...",
                "SELECT ... FROM testapp_book GROUP BY ...",
            ]
        )

    def test_options_returns_select2_results_for_choice_filter(self, admin_client):
        Book.objects.create(title="Dune", genre="fiction")
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = admin_client.get(
                url,
                {
                    "app_label": "testapp",
                    "model_name": "book",
                    "parameter_name": "genre",
                    "q": "Fic",
                },
            )

        assert response.status_code == 200
        results = response.json()["results"]
        assert results == [
            {"id": "__all__", "text": "All"},
            {"id": "fiction", "text": "Fiction"},
        ]
        assert queries == snapshot(
            [
                "SELECT ... FROM django_session WHERE ... LIMIT ...",
                "SELECT ... FROM auth_user WHERE ... LIMIT ...",
                "SELECT ... FROM testapp_book WHERE ...",
                "SELECT ... FROM testapp_book WHERE ... LIMIT ...",
            ]
        )

    def test_options_finds_a_model_registered_only_on_a_custom_admin_site(
        self, admin_client
    ):
        """A model registered only on a project's own AdminSite (not on
        django.contrib.admin.site) must still resolve; see ``Country``,
        registered solely on ``e2e_admin_site`` in tests/testapp/admin.py."""
        Country.objects.create(name="Chile")
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = admin_client.get(
                url,
                {
                    "app_label": "testapp",
                    "model_name": "country",
                    "parameter_name": "name",
                },
            )

        assert response.status_code == 200
        results = response.json()["results"]
        assert {"id": "Chile", "text": "Chile"} in results
        assert queries == snapshot(
            [
                "SELECT ... FROM django_session WHERE ... LIMIT ...",
                "SELECT ... FROM auth_user WHERE ... LIMIT ...",
            ]
        )


class Select2FilterOptionsViewMethodTests(TestCase):
    """Unit tests for the view's non-``get`` methods, called directly."""

    def setUp(self):
        self.view = Select2FilterOptionsView()

    def test__get_filter_class(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]

        with self.subTest("matches a plain filter class entry"):
            self.assertIs(
                self.view._get_filter_class(model_admin, request, "author"),
                AsyncAuthorFilter,
            )

        with self.subTest("matches a (field, filter) tuple entry"):

            class _TupleFilterAdmin(admin.ModelAdmin):
                list_filter = [("author", AsyncAuthorFilter)]

            tuple_admin = _TupleFilterAdmin(Book, admin.site)
            self.assertIs(
                self.view._get_filter_class(tuple_admin, request, "author"),
                AsyncAuthorFilter,
            )

        with self.subTest("ignores a non-async filter with a matching name"):
            self.assertIsNone(
                self.view._get_filter_class(model_admin, request, "not_a_real_field")
            )

        with self.subTest("returns None when nothing matches parameter_name"):
            self.assertIsNone(
                self.view._get_filter_class(model_admin, request, "unknown")
            )

    def test__has_view_permission(self):
        request = RequestFactory().get("/admin/")

        with self.subTest("model not registered on this site"):
            self.assertFalse(
                self.view._has_view_permission(admin.site, Country, request)
            )

        with self.subTest("registered but permission denied"):
            request.user = AnonymousUser()
            self.assertFalse(self.view._has_view_permission(admin.site, Book, request))

        with self.subTest("registered and permitted"):
            request.user = User.objects.create_superuser(
                "admin2", "admin2@example.com", "password"
            )
            self.assertTrue(self.view._has_view_permission(admin.site, Book, request))

    def test__find_admin_site(self):
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            "admin3", "admin3@example.com", "password"
        )
        permitted_site = admin.site

        class _DenyingModelAdmin(admin.ModelAdmin):
            def has_view_permission(self, request, obj=None):
                return False

        class _DenyingSite:
            _registry = {Book: _DenyingModelAdmin(Book, admin.site)}

        with self.subTest("skips a site without permission, returns the next match"):
            with patch(
                "django_admin_select_filter.views.all_sites",
                [_DenyingSite(), permitted_site],
            ):
                found = self.view._find_admin_site(Book, request, "author")
            self.assertIs(found, permitted_site)

        with self.subTest("returns None when no site has a matching filter"):
            with patch("django_admin_select_filter.views.all_sites", []):
                found = self.view._find_admin_site(Book, request, "author")
            self.assertIsNone(found)

    def test__find_admin_site_via_registry(self):
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            "admin4", "admin4@example.com", "password"
        )
        permitted_site = admin.site

        class _DenyingModelAdmin(admin.ModelAdmin):
            def has_view_permission(self, request, obj=None):
                return False

        class _DenyingSite:
            _registry = {Book: _DenyingModelAdmin(Book, admin.site)}

        class _EmptyListFilterModelAdmin(admin.ModelAdmin):
            list_filter = ()

        class _PermittedNoMatchSite:
            _registry = {Book: _EmptyListFilterModelAdmin(Book, admin.site)}

        Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        try:
            with self.subTest(
                "skips a site without permission, returns the next match"
            ):
                with patch(
                    "django_admin_select_filter.views.all_sites",
                    [_DenyingSite(), permitted_site],
                ):
                    Select2FilterOptionsView._build_async_filter_registry.cache_clear()
                    found = self.view._find_admin_site_via_registry(
                        Book, request, "author"
                    )
                self.assertIs(found, permitted_site)

            with self.subTest(
                "permitted site without a registry match, tries the next site"
            ):
                with patch(
                    "django_admin_select_filter.views.all_sites",
                    [_PermittedNoMatchSite(), permitted_site],
                ):
                    Select2FilterOptionsView._build_async_filter_registry.cache_clear()
                    found = self.view._find_admin_site_via_registry(
                        Book, request, "author"
                    )
                self.assertIs(found, permitted_site)

            with self.subTest("returns None when no site has a matching filter"):
                with patch("django_admin_select_filter.views.all_sites", []):
                    Select2FilterOptionsView._build_async_filter_registry.cache_clear()
                    found = self.view._find_admin_site_via_registry(
                        Book, request, "author"
                    )
                self.assertIsNone(found)
        finally:
            Select2FilterOptionsView._build_async_filter_registry.cache_clear()

    def test_build_async_filter_registry(self):
        Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        try:
            registry = Select2FilterOptionsView._build_async_filter_registry()
        finally:
            Select2FilterOptionsView._build_async_filter_registry.cache_clear()

        book_map = registry[admin.site]["testapp"]["book"]
        with self.subTest("includes an async foreign-key filter"):
            self.assertIs(book_map["author"], AsyncAuthorFilter)

        with self.subTest("includes an async choice filter"):
            self.assertIs(book_map["genre"], AsyncGenreFilter)

        with self.subTest("excludes sync filters sharing the same parameter_name"):
            self.assertIsNot(book_map["genre"], GenreFilter)

    def test_get_with_use_registry(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get(
            "/",
            {
                "app_label": "testapp",
                "model_name": "book",
                "parameter_name": "author",
            },
        )
        request.user = User.objects.create_superuser(
            "admin5", "admin5@example.com", "password"
        )

        Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        try:
            view = Select2FilterOptionsView.as_view(use_registry=True)
            response = view(request)
        finally:
            Select2FilterOptionsView._build_async_filter_registry.cache_clear()

        self.assertEqual(response.status_code, 200)
        results = json.loads(response.content)["results"]
        self.assertIn({"id": str(author.pk), "text": "Rowling"}, results)
