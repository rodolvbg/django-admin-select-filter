"""ChoiceFilter: options from values and labels."""

import pytest
from django.contrib import admin
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from unittest_parametrize import ParametrizedTestCase

from django_admin_select_filter.filters import (
    ChoiceFilter,
)
from tests.cases import _adapt_filter_params_to_django_version, _FakeChangeList
from tests.testapp.admin import (
    AllGenresFilter,
    AsyncGenreFilter,
    AuthorStatusFilter,
    ExplicitOptionsGenreFilter,
    ExplicitOptionsMissingFieldFilter,
    FixedTitleGenreFilter,
    GenreFilter,
    MultipleAsyncGenreFilter,
    MultipleGenreFilter,
    NonRelationChainFilter,
    NonSearchableGenreFilter,
    UnknownChainFilter,
)
from tests.testapp.models import Author, Book


class TestChoiceFilter(ParametrizedTestCase, TestCase):
    """The choices flavour: options from field choices or explicit ones."""

    def setUp(self):
        patcher = _adapt_filter_params_to_django_version()
        patcher.start()
        self.addCleanup(patcher.stop)

    def _build_filter(self, filter_class, request, params=None):
        model_admin = admin.site._registry[Book]
        return filter_class(request, params or {}, Book, model_admin)

    def test_derives_options_from_field_choices(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(AllGenresFilter, request)

        assert filter_instance.options == [
            ("fiction", "Fiction"),
            ("nonfiction", "Non-fiction"),
            ("poetry", "Poetry"),
        ]
        assert filter_instance.title == "genre"

    def test_template_renders_select2_markup(self):
        Book.objects.create(title="Dune", genre="fiction")

        request = RequestFactory().get("/admin/tests/book/")
        filter_instance = self._build_filter(GenreFilter, request)

        html = render_to_string(
            filter_instance.template,
            {
                "spec": filter_instance,
                "title": filter_instance.title,
                "choices": list(filter_instance.choices(_FakeChangeList())),
            },
            request=request,
        )

        assert 'class="django-admin-select-filter"' in html
        assert 'data-parameter-name="genre"' in html
        assert "Fiction" in html

    def test_template_omits_searchable_attribute_by_default(
        self,
    ):
        request = RequestFactory().get("/admin/")

        filter_instance = self._build_filter(GenreFilter, request)
        html = render_to_string(
            filter_instance.template,
            {
                "spec": filter_instance,
                "title": filter_instance.title,
                "choices": list(filter_instance.choices(_FakeChangeList())),
            },
            request=request,
        )
        assert "data-searchable" not in html

    def test_template_renders_searchable_attribute_when_disabled(self):
        request = RequestFactory().get("/admin/")

        filter_instance = self._build_filter(NonSearchableGenreFilter, request)
        html = render_to_string(
            filter_instance.template,
            {
                "spec": filter_instance,
                "title": filter_instance.title,
                "choices": list(filter_instance.choices(_FakeChangeList())),
            },
            request=request,
        )
        assert 'data-searchable="false"' in html

    def test_explicit_title_skips_default_lookup(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(FixedTitleGenreFilter, request)

        assert filter_instance.title == "Fixed title"

    def test_title_falls_back_to_parameter_name_for_missing_field(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(ExplicitOptionsMissingFieldFilter, request)

        assert filter_instance.title == "not_a_real_field"

    def test_derives_options_from_nested_parameter_name(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(AuthorStatusFilter, request)

        assert filter_instance.options == [
            ("active", "Active"),
            ("retired", "Retired"),
        ]
        assert filter_instance.title == "status"

    def test_queryset_filters_by_selected_nested_status(self):
        active = Author.objects.create(name="Active One", status="active")
        Author.objects.create(name="Retired One", status="retired")
        Book.objects.create(title="A", author=active)

        request = RequestFactory().get(
            "/admin/tests/book/", {"author__status": "active"}
        )
        filter_instance = self._build_filter(
            AuthorStatusFilter, request, {"author__status": ["active"]}
        )

        result = filter_instance.queryset(request, Book.objects.all())

        assert list(result.values_list("title", flat=True)) == ["A"]

    def test_options_not_resolved_past_an_unknown_chain_segment(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(UnknownChainFilter, request)

        assert filter_instance.title == "bogus__status"

    def test_options_not_resolved_past_a_non_relation_chain_segment(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(NonRelationChainFilter, request)

        assert filter_instance.title == "title__status"

    def test_requires_parameter_name(self):
        class InvalidFilter(ChoiceFilter):
            pass

        with pytest.raises(TypeError, match="parameter_name must be configured"):
            InvalidFilter(
                RequestFactory().get("/admin/"), {}, Book, admin.site._registry[Book]
            )

    def test_requires_options_or_field_choices(self):
        class InvalidFilter(ChoiceFilter):
            parameter_name = "title"

        with pytest.raises(TypeError, match="options must be configured"):
            InvalidFilter(
                RequestFactory().get("/admin/"), {}, Book, admin.site._registry[Book]
            )

    def test_accepts_explicit_options(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(ExplicitOptionsGenreFilter, request)

        assert filter_instance.options == [("fiction", "Fiction"), ("poetry", "Poetry")]

    def test_queryset_filters_by_selected_genre(self):
        Book.objects.create(title="Dune", genre="fiction")
        Book.objects.create(title="Cosmos", genre="nonfiction")

        request = RequestFactory().get("/admin/tests/book/", {"genre": "fiction"})
        filter_instance = self._build_filter(
            GenreFilter, request, {"genre": ["fiction"]}
        )

        result = filter_instance.queryset(request, Book.objects.all())

        assert list(result.values_list("title", flat=True)) == ["Dune"]

    def test_get_options_only_used_values_by_default(self):
        Book.objects.create(title="Dune", genre="fiction")
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(GenreFilter, request)
        assert filter_instance.get_options() == [("fiction", "Fiction")]

    def test_get_options_all_values_when_filter_only_used_values_is_false(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(AllGenresFilter, request)
        assert filter_instance.get_options() == [
            ("fiction", "Fiction"),
            ("nonfiction", "Non-fiction"),
            ("poetry", "Poetry"),
        ]

    def test_get_options_searches_by_label_substring(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(AllGenresFilter, request)
        assert filter_instance.get_options(q="fic") == [
            ("fiction", "Fiction"),
            ("nonfiction", "Non-fiction"),
        ]

    def test__option_items(self):
        Book.objects.create(title="Dune", genre="fiction")
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(GenreFilter, request)
        assert filter_instance._option_items(
            request=RequestFactory().get("/api/"), q=""
        ) == [("fiction", "Fiction")]

    def test__selected_option_items_no_selection_returns_empty(self):
        request = RequestFactory().get("/admin/tests/book/")
        filter_instance = self._build_filter(AsyncGenreFilter, request)
        assert filter_instance._selected_option_items() == []

    def test__selected_option_items_single_selection_returns_the_matching_option(self):
        request = RequestFactory().get("/admin/tests/book/", {"genre": "fiction"})
        filter_instance = self._build_filter(
            AsyncGenreFilter, request, {"genre": ["fiction"]}
        )
        assert filter_instance._selected_option_items() == [("fiction", "Fiction")]

    def test__selected_option_items_multiple_selection_returns_every_selected_option(
        self,
    ):
        request = RequestFactory().get(
            "/admin/tests/book/", {"genre": "fiction,poetry"}
        )
        filter_instance = self._build_filter(
            MultipleAsyncGenreFilter, request, {"genre": ["fiction,poetry"]}
        )
        assert set(filter_instance._selected_option_items()) == {
            ("fiction", "Fiction"),
            ("poetry", "Poetry"),
        }

    def test_multiple_selection(self):
        Book.objects.create(title="Dune", genre="fiction")
        Book.objects.create(title="Cosmos", genre="poetry")

        request = RequestFactory().get(
            "/admin/tests/book/", {"genre": "fiction,poetry"}
        )
        filter_instance = self._build_filter(
            MultipleGenreFilter, request, {"genre": ["fiction,poetry"]}
        )
        result = filter_instance.queryset(request, Book.objects.all())
        assert set(result.values_list("title", flat=True)) == {"Dune", "Cosmos"}
