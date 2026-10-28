"""ForeignKeyFilter: options from related objects."""

import re
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_admin_select_filter.filters import (
    BaseSelectFilter,
    ForeignKeyFilter,
)
from tests.cases import (
    _adapt_filter_params_to_django_version,
    _FakeChangeList,
)
from tests.testapp.admin import (
    AllNullableAuthorFilter,
    AsyncAuthorFilter,
    AuthorFilter,
    ExplicitNullableAuthorFilter,
    FixedTitleAuthorFilter,
    MissingFieldFilter,
    MultipleAsyncAuthorFilter,
    MultipleAuthorFilter,
    OnlyNameAuthorFilter,
)
from tests.testapp.models import Author, Book, Country


class TestForeignKeyFilter(ParametrizedTestCase, TestCase):
    """The foreign-key flavour: model inference, options and rendering."""

    def setUp(self):
        patcher = _adapt_filter_params_to_django_version()
        patcher.start()
        self.addCleanup(patcher.stop)

    def _build_filter(self, request, params=None):
        model_admin = admin.site._registry[Book]
        return AuthorFilter(request, params or {}, Book, model_admin)

    @parametrize(
        ("parameter_name", "expected"),
        [
            (None, None),
            ("does_not_exist", None),
            ("author", Author),
            ("author__country", Country),
            ("title", None),
        ],
        ids=[
            "no_parameter_name",
            "unknown_field",
            "plain_relation_field",
            "nested_relation_chain",
            "final_segment_isn_t_a_relation",
        ],
    )
    def test__resolve_model(self, parameter_name, expected):
        filter_instance = ForeignKeyFilter.__new__(ForeignKeyFilter)
        filter_instance.parameter_name = parameter_name

        assert filter_instance._resolve_model(Book) is expected

    def test_get_options_only_used_values_by_default(self):
        used = Author.objects.create(name="Used")
        Author.objects.create(name="Unused")
        Book.objects.create(title="A Book", author=used)
        request = RequestFactory().get("/admin/tests/book/")
        filter_instance = self._build_filter(request)
        assert list(filter_instance.get_options()) == [used]

    def test_get_options_all_values_when_filter_only_used_values_is_false(self):
        unused = Author.objects.create(name="Unused")
        request = RequestFactory().get("/admin/")
        filter_instance = AllNullableAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )
        assert list(filter_instance.get_options()) == [unused]

    def test_get_options_respects_only_fields(self):
        author = Author.objects.create(name="Solo")
        Book.objects.create(title="Book", author=author)
        request = RequestFactory().get("/admin/")
        filter_instance = OnlyNameAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )
        assert list(filter_instance.get_options()) == [author]

    def test_get_options_searches_related_admin(self):
        match = Author.objects.create(name="Rowling")
        Author.objects.create(name="Tolkien")
        Book.objects.create(title="HP", author=match)
        Book.objects.create(title="LOTR", author=Author.objects.get(name="Tolkien"))
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(request)
        assert list(filter_instance.get_options(q="Rowl")) == [match]

    def test_get_options_deduplicates_when_related_admin_reports_duplicates(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        related_admin = admin.site._registry[Author]
        with patch.object(
            related_admin,
            "get_search_results",
            lambda request, queryset, search_term: (queryset, True),
        ):
            request = RequestFactory().get("/admin/")
            filter_instance = self._build_filter(request)
            assert list(filter_instance.get_options(q="anything")) == [author]

    def test__option_items(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(request)
        assert filter_instance._option_items(
            request=RequestFactory().get("/api/"), q=""
        ) == [(str(author.pk), "Rowling")]

    def test__selected_option_items_no_selection_returns_empty(self):
        request = RequestFactory().get("/admin/tests/book/")
        filter_instance: BaseSelectFilter = AsyncAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )
        assert filter_instance._selected_option_items() == []

    def test__selected_option_items_single_selection_returns_the_matching_instance(
        self,
    ):
        author = Author.objects.create(name="Tolkien")
        request = RequestFactory().get("/admin/tests/book/", {"author": str(author.pk)})
        filter_instance = AsyncAuthorFilter(
            request,
            {"author": [str(author.pk)]},
            Book,
            admin.site._registry[Book],
        )
        assert filter_instance._selected_option_items() == [(str(author.pk), "Tolkien")]

    def test__selected_option_items_multiple_selection_returns_every_selected_instance(
        self,
    ):
        rowling = Author.objects.create(name="Rowling")
        tolkien = Author.objects.create(name="Tolkien2")
        request = RequestFactory().get(
            "/admin/tests/book/",
            {"author": f"{rowling.pk},{tolkien.pk}"},
        )
        filter_instance = MultipleAsyncAuthorFilter(
            request,
            {"author": [f"{rowling.pk},{tolkien.pk}"]},
            Book,
            admin.site._registry[Book],
        )
        assert set(filter_instance._selected_option_items()) == {
            (str(rowling.pk), "Rowling"),
            (str(tolkien.pk), "Tolkien2"),
        }

    def test_multiple_selection(self):
        rowling = Author.objects.create(name="Rowling")
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="HP", author=rowling)
        Book.objects.create(title="LOTR", author=tolkien)
        Book.objects.create(title="Solo", author=None)

        request = RequestFactory().get(
            "/admin/tests/book/",
            {"author": f"{rowling.pk},{tolkien.pk}"},
        )
        filter_instance = MultipleAuthorFilter(
            request,
            {"author": [f"{rowling.pk},{tolkien.pk}"]},
            Book,
            admin.site._registry[Book],
        )
        result = filter_instance.queryset(request, Book.objects.all())
        assert set(result.values_list("title", flat=True)) == {"HP", "LOTR"}

    def test_queryset_filters_by_selected_author(self):
        factory = RequestFactory()
        rowling = Author.objects.create(name="Rowling")
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="Harry Potter", author=rowling)
        Book.objects.create(title="The Hobbit", author=tolkien)

        request = factory.get("/admin/tests/book/", {"author": str(rowling.pk)})
        filter_instance = self._build_filter(request, {"author": [str(rowling.pk)]})

        result = filter_instance.queryset(request, Book.objects.all())

        assert list(result.values_list("title", flat=True)) == ["Harry Potter"]

    def test_null_option_present_when_null_books_exist(self):
        factory = RequestFactory()
        Book.objects.create(title="Orphan Book", author=None)

        request = factory.get("/admin/tests/book/")
        filter_instance = self._build_filter(request)

        assert filter_instance.has_null_option is True

    def test_template_renders_select2_markup(self):
        factory = RequestFactory()
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="Harry Potter", author=author)

        request = factory.get("/admin/tests/book/")
        filter_instance = self._build_filter(request)

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
        assert 'data-parameter-name="author"' in html
        assert "Rowling" in html
        assert "data-theme" not in html

        filter_instance.theme = "admin-autocomplete"
        html = render_to_string(
            filter_instance.template,
            {"spec": filter_instance, "title": filter_instance.title, "choices": []},
            request=request,
        )
        assert 'data-theme="admin-autocomplete"' in html

    def test_template_renders_multiple_select_markup(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="Harry Potter", author=author)

        request = RequestFactory().get("/admin/tests/book/", {"author": str(author.pk)})
        filter_instance = MultipleAuthorFilter(
            request, {"author": [str(author.pk)]}, Book, admin.site._registry[Book]
        )

        html = render_to_string(
            filter_instance.template,
            {
                "spec": filter_instance,
                "title": filter_instance.title,
                "choices": list(filter_instance.choices(_FakeChangeList())),
            },
            request=request,
        )

        select_tag = html[
            html.index("<select") : html.index(">", html.index("<select"))
        ]
        assert re.search(r"(?<!-)\bmultiple\b(?!-)", select_tag)
        assert 'data-multiple="true"' in html
        assert 'data-multiple-separator=","' in html
        assert f'value="{author.pk}"' in html
        assert "All</option>" not in html

    def test_missing_model_is_rejected_when_not_inferable(self):
        class InvalidFilter(ForeignKeyFilter):
            parameter_name = "title"  # a plain CharField, not a relation

        with pytest.raises(TypeError, match="model must be configured"):
            InvalidFilter(
                RequestFactory().get("/admin/"), {}, Book, admin.site._registry[Book]
            )

    def test_missing_model_is_rejected_without_parameter_name(self):
        class InvalidFilter(ForeignKeyFilter):
            pass

        with pytest.raises(TypeError, match="model must be configured"):
            InvalidFilter(
                RequestFactory().get("/admin/"), {}, Book, admin.site._registry[Book]
            )

    def test_model_is_inferred_from_parameter_name(self):
        class InferredAuthorFilter(ForeignKeyFilter):
            parameter_name = "author"

        request = RequestFactory().get("/admin/")
        filter_instance = InferredAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        assert filter_instance.model is Author

    def test_model_is_inferred_from_nested_parameter_name(self):
        class InferredCountryFilter(ForeignKeyFilter):
            parameter_name = "author__country"

        request = RequestFactory().get("/admin/")
        filter_instance = InferredCountryFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        assert filter_instance.model is Country

    def test_model_is_not_inferred_for_unknown_field(self):
        class InferredUnknownFieldFilter(ForeignKeyFilter):
            parameter_name = "not_a_real_field"

        request = RequestFactory().get("/admin/")

        with pytest.raises(TypeError, match="model must be configured"):
            InferredUnknownFieldFilter(request, {}, Book, admin.site._registry[Book])

    def test_model_is_not_inferred_past_a_non_relation_field(self):
        class InferredNestedFilter(ForeignKeyFilter):
            parameter_name = "author__name"

        request = RequestFactory().get("/admin/")

        with pytest.raises(TypeError, match="model must be configured"):
            InferredNestedFilter(request, {}, Book, admin.site._registry[Book])

    def test_explicit_title_skips_default_lookup(self):
        request = RequestFactory().get("/admin/")
        filter_instance = FixedTitleAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        assert filter_instance.title == "Fixed title"

    def test_title_is_the_fields_as_in_django(self):
        """The field's verbose name, as Django's RelatedFieldListFilter: a
        filter of ``Book.author`` is "author", not "authors"."""
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]

        class CountryFilter(ForeignKeyFilter):
            parameter_name = "author__country"

        class BooksFilter(ForeignKeyFilter):
            parameter_name = "books"  # A reverse relation: no verbose name.

        assert AuthorFilter(request, {}, Book, model_admin).title == "author"
        assert CountryFilter(request, {}, Book, model_admin).title == "country"
        books = BooksFilter(request, {}, Author, admin.site._registry[Author])
        assert books.title == "book"
        # No such field (an explicit model): the model's.
        assert MissingFieldFilter(request, {}, Book, model_admin).title == "author"

    def test_explicit_nullable_skips_field_inference(self):
        request = RequestFactory().get("/admin/")
        filter_instance = ExplicitNullableAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        assert filter_instance.nullable is False
        assert filter_instance.has_null_option is False

    def test_missing_field_is_not_nullable(self):
        request = RequestFactory().get("/admin/")
        filter_instance = MissingFieldFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        assert filter_instance.nullable is False
        assert filter_instance.has_null_option is False

    def test_filter_only_used_values_false_always_shows_null_option(self):
        request = RequestFactory().get("/admin/")
        filter_instance = AllNullableAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        assert filter_instance.has_null_option is True

    def test_missing_parameter_name_short_circuits_facet_counts_and_queryset(self):
        filter_instance = ForeignKeyFilter.__new__(ForeignKeyFilter)
        filter_instance.used_parameters = {}
        queryset = Book.objects.all()

        assert filter_instance._get_option_facet_counts() == {}
        assert (
            filter_instance.queryset(RequestFactory().get("/admin/"), queryset)
            is queryset
        )

    def test_queryset_without_selected_value_is_unchanged(self):
        request = RequestFactory().get("/admin/tests/book/")
        filter_instance = self._build_filter(request)
        queryset = Book.objects.all()

        assert filter_instance.queryset(request, queryset) is queryset

    def test_queryset_null_value_filters_null_relations(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        null_value = AllNullableAuthorFilter.null_value
        request = RequestFactory().get("/admin/tests/book/", {"author": null_value})
        filter_instance = AllNullableAuthorFilter(
            request, {"author": [null_value]}, Book, admin.site._registry[Book]
        )

        result = filter_instance.queryset(request, Book.objects.all())

        assert list(result.values_list("title", flat=True)) == ["Orphan"]

    def test_has_output_true_for_async_filter_without_options(self):
        request = RequestFactory().get("/admin/tests/book/")
        filter_instance = AsyncAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        assert filter_instance.has_output() is True

    def test_has_output_false_when_no_options_available(self):
        request = RequestFactory().get("/admin/tests/book/")
        filter_instance = self._build_filter(request)

        assert filter_instance.has_output() is False
