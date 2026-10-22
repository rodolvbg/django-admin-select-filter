import json
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from inline_snapshot import snapshot
from inline_snapshot_django import snapshot_queries

from django_admin_select_filter.views import Select2FilterOptionsView
from tests.testapp.admin import AsyncAuthorFilter, AsyncGenreFilter, GenreFilter
from tests.testapp.models import Author, Book, Country


class TestSelect2FilterOptionsView(TestCase):
    """The options endpoint, end to end."""

    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )

    def setUp(self):
        self.client.force_login(self.user)

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

    def test_options_404_when_no_matching_filter(self):
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = self.client.get(
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

    def test_options_404_for_non_async_filter(self):
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = self.client.get(
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

    def test_options_returns_select2_results_for_foreign_key_filter(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="Harry Potter", author=author)
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = self.client.get(
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

    def test_options_returns_select2_results_for_choice_filter(self):
        Book.objects.create(title="Dune", genre="fiction")
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = self.client.get(
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

    def test_options_finds_a_model_registered_only_on_a_custom_admin_site(self):
        """A model registered only on a project's own AdminSite (not on
        django.contrib.admin.site) must still resolve; see ``Country``,
        registered solely on ``e2e_admin_site`` in tests/testapp/admin.py."""
        Country.objects.create(name="Chile")
        url = reverse("admin_select_filter:options")

        with snapshot_queries() as queries:
            response = self.client.get(
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


class TestSelect2FilterOptionsViewMethods(TestCase):
    """Unit tests for the view's non-``get`` methods, called directly."""

    def setUp(self):
        self.view = Select2FilterOptionsView()
        Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        self.addCleanup(
            Select2FilterOptionsView._build_async_filter_registry.cache_clear
        )

    def test__get_filter_class_matches_a_plain_filter_class_entry(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]

        assert (
            self.view._get_filter_class(model_admin, request, "author")
            is AsyncAuthorFilter
        )

    def test__get_filter_class_matches_a_field_filter_tuple_entry(self):
        request = RequestFactory().get("/admin/")

        class _TupleFilterAdmin(admin.ModelAdmin[Book]):
            # Not a real FieldListFilter tuple (Django's stub rejects a
            # bare BaseSelectFilter subclass here) — only exercises
            # _get_filter_class()'s own tuple-unpacking, never Django's
            # actual FieldListFilter calling convention.
            list_filter = [("author", AsyncAuthorFilter)]  # type: ignore[list-item]

        tuple_admin = _TupleFilterAdmin(Book, admin.site)
        assert (
            self.view._get_filter_class(tuple_admin, request, "author")
            is AsyncAuthorFilter
        )

    def test__get_filter_class_ignores_a_non_async_filter_with_a_matching_name(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]

        assert (
            self.view._get_filter_class(model_admin, request, "not_a_real_field")
            is None
        )

    def test__get_filter_class_returns_none_when_nothing_matches_parameter_name(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]

        assert self.view._get_filter_class(model_admin, request, "unknown") is None

    def test__has_view_permission_model_not_registered_on_this_site(self):
        request = RequestFactory().get("/admin/")

        assert not self.view._has_view_permission(admin.site, Country, request)

    def test__has_view_permission_registered_but_permission_denied(self):
        request = RequestFactory().get("/admin/")

        request.user = AnonymousUser()
        assert not self.view._has_view_permission(admin.site, Book, request)

    def test__has_view_permission_registered_and_permitted(self):
        request = RequestFactory().get("/admin/")

        request.user = User.objects.create_superuser(
            "admin2", "admin2@example.com", "password"
        )
        assert self.view._has_view_permission(admin.site, Book, request)

    def test__find_admin_site_skips_a_site_without_permission_returns_the_next_match(
        self,
    ):
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            "admin3", "admin3@example.com", "password"
        )
        permitted_site = admin.site

        class _DenyingModelAdmin(admin.ModelAdmin[Book]):
            def has_view_permission(self, request, obj=None):
                return False

        class _DenyingSite:
            _registry = {Book: _DenyingModelAdmin(Book, admin.site)}

        with patch(
            "django_admin_select_filter.views.all_sites",
            [_DenyingSite(), permitted_site],
        ):
            found = self.view._find_admin_site(Book, request, "author")
        assert found is permitted_site

    def test__find_admin_site_returns_none_when_no_site_has_a_matching_filter(self):
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            "admin3", "admin3@example.com", "password"
        )

        with patch("django_admin_select_filter.views.all_sites", []):
            found = self.view._find_admin_site(Book, request, "author")
        assert found is None

    def _via_registry(self, sites):
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            "admin4", "admin4@example.com", "password"
        )
        with patch("django_admin_select_filter.views.all_sites", sites):
            Select2FilterOptionsView._build_async_filter_registry.cache_clear()
            return self.view._find_admin_site_via_registry(Book, request, "author")

    def test__find_admin_site_via_registry_skips_a_site_without_permission(self):
        class _DenyingModelAdmin(admin.ModelAdmin[Book]):
            def has_view_permission(self, request, obj=None):
                return False

        class _DenyingSite:
            _registry = {Book: _DenyingModelAdmin(Book, admin.site)}

        found = self._via_registry([_DenyingSite(), admin.site])

        assert found is admin.site

    def test__find_admin_site_via_registry_tries_next_site_without_a_registry_match(
        self,
    ):
        class _EmptyListFilterModelAdmin(admin.ModelAdmin[Book]):
            list_filter = ()

        class _PermittedNoMatchSite:
            _registry = {Book: _EmptyListFilterModelAdmin(Book, admin.site)}

        found = self._via_registry([_PermittedNoMatchSite(), admin.site])

        assert found is admin.site

    def test__find_admin_site_via_registry_returns_none_when_no_site_matches(self):
        found = self._via_registry([])

        assert found is None

    def test_build_async_filter_registry_includes_an_async_foreign_key_filter(self):
        Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        try:
            registry = Select2FilterOptionsView._build_async_filter_registry()
        finally:
            Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        book_map = registry[admin.site]["testapp"]["book"]

        assert book_map["author"] is AsyncAuthorFilter

    def test_build_async_filter_registry_includes_an_async_choice_filter(self):
        Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        try:
            registry = Select2FilterOptionsView._build_async_filter_registry()
        finally:
            Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        book_map = registry[admin.site]["testapp"]["book"]

        assert book_map["genre"] is AsyncGenreFilter

    def test_build_async_filter_registry_excludes_sync_filters_sharing_the_same_parameter_name(
        self,
    ):
        Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        try:
            registry = Select2FilterOptionsView._build_async_filter_registry()
        finally:
            Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        book_map = registry[admin.site]["testapp"]["book"]

        assert book_map["genre"] is not GenreFilter

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

        assert response.status_code == 200
        assert isinstance(response, HttpResponse)
        results = json.loads(response.content)["results"]
        assert {"id": str(author.pk), "text": "Rowling"} in results
