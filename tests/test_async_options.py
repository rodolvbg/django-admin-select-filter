"""AsyncOptionsMixin: options loaded through an API."""

import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse

from django_admin_select_filter.filters import (
    BaseSelectFilter,
)
from tests.cases import SelectFilterCase
from tests.testapp.admin import (
    AsyncAuthorFilter,
    AuthorFilter,
)
from tests.testapp.models import Author, Book


class TestAsyncOptionsMixin(SelectFilterCase):
    """AsyncOptionsMixin: options loaded through an API."""

    def test_async_call_url_class_default_is_none(self):
        assert BaseSelectFilter.async_call_url is None

    def test_async_call_url_resolved_via_reverse_when_async_and_unset(self):
        request = RequestFactory().get("/admin/")
        filter_instance: BaseSelectFilter = AsyncAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )
        assert filter_instance.async_call_url == reverse("admin_select_filter:options")

    def test_async_call_url_left_as_none_when_not_async(self):
        request = RequestFactory().get("/admin/")
        filter_instance = AuthorFilter(request, {}, Book, admin.site._registry[Book])
        assert filter_instance.async_call_url is None

    def test_async_call_url_explicit_override_is_preserved(self):
        class CustomAsyncFilter(AsyncAuthorFilter):
            async_call_url = "/custom/options/"

        request = RequestFactory().get("/admin/")
        filter_instance = CustomAsyncFilter(
            request, {}, Book, admin.site._registry[Book]
        )
        assert filter_instance.async_call_url == "/custom/options/"

    def test__get_option_facet_counts_no_parameter_name(self):
        Book.objects.create(title="A", genre="fiction")
        Book.objects.create(title="B", genre="fiction")
        Book.objects.create(title="C", genre="poetry")
        Book.objects.create(title="D", genre=None)
        model_admin = admin.site._registry[Book]
        request = RequestFactory().get("/admin/")

        filter_instance = self._build(
            parameter_name=None, model_admin=model_admin, request=request
        )
        assert filter_instance._get_option_facet_counts() == {}

    def test__get_option_facet_counts_grouped_counts_including_null(self):
        Book.objects.create(title="A", genre="fiction")
        Book.objects.create(title="B", genre="fiction")
        Book.objects.create(title="C", genre="poetry")
        Book.objects.create(title="D", genre=None)
        model_admin = admin.site._registry[Book]
        request = RequestFactory().get("/admin/")

        filter_instance = self._build(
            parameter_name="genre", model_admin=model_admin, request=request
        )
        assert filter_instance._get_option_facet_counts() == {
            "fiction": 2,
            "poetry": 1,
            filter_instance.null_value: 1,
        }

    def test__build_async_options_plain_no_null_option_no_facets(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        Book.objects.create(title="Orphan", author=None)
        model_admin = admin.site._registry[Book]
        items = [(str(author.pk), "Rowling")]

        filter_instance = self._build(
            nullable=False,
            parameter_name="author",
            model_admin=model_admin,
            request=RequestFactory().get("/admin/"),
        )
        options = filter_instance._build_async_options(
            RequestFactory().get("/api/"), items
        )
        assert options == [("__all__", "All"), *items]

    def test__build_async_options_null_option_appended(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        Book.objects.create(title="Orphan", author=None)
        model_admin = admin.site._registry[Book]
        items = [(str(author.pk), "Rowling")]

        filter_instance = self._build(
            nullable=True,
            parameter_name="author",
            filter_only_used_values=False,
            model_admin=model_admin,
            request=RequestFactory().get("/admin/"),
        )
        options = filter_instance._build_async_options(
            RequestFactory().get("/api/"), items
        )
        assert options == [("__all__", "All"), *items, ("__null__", "-")]

    def test__build_async_options_facet_counts_on_every_non_all_option(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        Book.objects.create(title="Orphan", author=None)
        model_admin = admin.site._registry[Book]
        items = [(str(author.pk), "Rowling")]

        filter_instance = self._build(
            nullable=True,
            parameter_name="author",
            filter_only_used_values=False,
            model_admin=model_admin,
            request=RequestFactory().get("/admin/"),
        )
        options = filter_instance._build_async_options(
            RequestFactory().get("/api/", {"facets": "true"}), items
        )
        assert options == [
            ("__all__", "All"),
            (str(author.pk), "Rowling (1)"),
            ("__null__", "- (1)"),
        ]

    def test_has_output_async_filter_always_has_output(self):
        filter_instance = self._build(async_call=True, lookup_choices=[])
        assert filter_instance.has_output()

    def test_media_async_call_adds_async_options_js(self):
        filter_instance = self._build(async_call=True)
        assert "admin_select_filter/js/async_options.js" in str(
            filter_instance.media["js"]
        )

    def test_get_async_options_requires_option_items(
        self,
    ):
        filter_instance = self._build()
        with pytest.raises(NotImplementedError):
            filter_instance.get_async_options(RequestFactory().get("/api/"), "")

    def test_get_async_options_delegates_to_option_items(self):
        filter_instance = self._build(
            nullable=False,
            parameter_name="x",
            _option_items=lambda request=None, q="": [("1", "One")],
        )
        options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")
        assert options == [(filter_instance.all_value, "All"), ("1", "One")]

    def test_lookups_requires_selected_option_items_when_async(
        self,
    ):
        filter_instance = self._build(async_call=True)
        with pytest.raises(NotImplementedError):
            filter_instance.lookups(RequestFactory().get("/admin/"), None)

    def test_lookups_in_async_mode_uses_selected_option_items(
        self,
    ):
        filter_instance = self._build(
            async_call=True,
            has_null_option=False,
            _option_items=lambda request=None, q="": [],
            _selected_option_items=lambda: [("2", "Two")],
        )
        result = filter_instance.lookups(RequestFactory().get("/admin/"), None)
        assert result == [("2", "Two")]
