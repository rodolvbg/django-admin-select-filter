import pytest
from django.contrib import admin
from django.template.loader import render_to_string
from django.test import RequestFactory

from django_admin_select_filter.filters import (
    BaseSelectFilter,
    ChoiceFilter,
    ForeignKeyFilter,
)
from tests.testapp.admin import (
    AllGenresFilter,
    AllNullableAuthorFilter,
    AsyncAuthorFilter,
    AsyncGenreFilter,
    AuthorFilter,
    AuthorStatusFilter,
    ExplicitNullableAuthorFilter,
    ExplicitOptionsGenreFilter,
    ExplicitOptionsMissingFieldFilter,
    FixedTitleAuthorFilter,
    FixedTitleGenreFilter,
    GenreFilter,
    MissingFieldFilter,
    NonRelationChainFilter,
    OnlyNameAuthorFilter,
    UnknownChainFilter,
)
from tests.testapp.models import Author, Book, Country

pytestmark = pytest.mark.django_db


class _FakeChangeList:
    add_facets = False

    def get_query_string(self, new_params=None, remove=None):
        return "?author=1"


class TestBaseSelectFilter:
    def test_get_async_options_is_abstract(self):
        filter_instance = BaseSelectFilter.__new__(BaseSelectFilter)

        with pytest.raises(NotImplementedError):
            filter_instance.get_async_options(RequestFactory().get("/api/"), "")


class TestForeignKeyFilter:
    def _build_filter(self, request, params=None):
        model_admin = admin.site._registry[Book]
        return AuthorFilter(request, params or {}, Book, model_admin)

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

    def test_get_options_only_returns_used_authors(self):
        factory = RequestFactory()
        used = Author.objects.create(name="Used")
        Author.objects.create(name="Unused")
        Book.objects.create(title="A Book", author=used)

        request = factory.get("/admin/tests/book/")
        filter_instance = self._build_filter(request)

        assert list(filter_instance.get_options()) == [used]

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
        assert 'data-autocomplete="true"' in html
        assert "Rowling" in html

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

    def test_get_options_without_used_filter_returns_all_authors(self):
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

    def test_get_options_deduplicates_when_related_admin_reports_duplicates(
        self, monkeypatch
    ):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        related_admin = admin.site._registry[Author]
        monkeypatch.setattr(
            related_admin,
            "get_search_results",
            lambda request, queryset, term: (queryset, True),
        )

        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(request)

        assert list(filter_instance.get_options(q="anything")) == [author]

    def test_get_async_options_lists_all_and_selected(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)

        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(request)

        options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")

        assert options == [
            (filter_instance.all_value, "All"),
            (str(author.pk), "Rowling"),
        ]

    def test_get_async_options_includes_null_value(self):
        request = RequestFactory().get("/admin/")
        filter_instance = AllNullableAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")

        assert options[-1] == (filter_instance.null_value, "-")

    def test_get_async_options_applies_facet_counts(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        Book.objects.create(title="Orphan", author=None)

        request = RequestFactory().get("/admin/")
        filter_instance = AllNullableAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        options = filter_instance.get_async_options(
            RequestFactory().get("/api/", {"facets": "true"}), ""
        )

        assert options[0] == (filter_instance.all_value, "All")
        assert (str(author.pk), "Rowling (1)") in options
        assert (filter_instance.null_value, "- (1)") in options

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

    def test_async_lookups_returns_empty_without_selection(self):
        request = RequestFactory().get("/admin/tests/book/")
        filter_instance = AsyncAuthorFilter(
            request, {}, Book, admin.site._registry[Book]
        )

        assert filter_instance.lookups(request, admin.site._registry[Book]) == []

    def test_async_lookups_returns_selected_instance(self):
        author = Author.objects.create(name="Rowling")

        request = RequestFactory().get("/admin/tests/book/", {"author": str(author.pk)})
        filter_instance = AsyncAuthorFilter(
            request, {"author": [str(author.pk)]}, Book, admin.site._registry[Book]
        )

        assert filter_instance.lookups(request, admin.site._registry[Book]) == [
            (str(author.pk), "Rowling")
        ]

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


class TestChoiceFilter:
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

    def test_get_options_only_returns_used_values(self):
        Book.objects.create(title="Dune", genre="fiction")

        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(GenreFilter, request)

        assert filter_instance.get_options() == [("fiction", "Fiction")]

    def test_get_options_without_used_filter_returns_all(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(AllGenresFilter, request)

        assert filter_instance.get_options() == [
            ("fiction", "Fiction"),
            ("nonfiction", "Non-fiction"),
            ("poetry", "Poetry"),
        ]

    def test_get_options_searches_by_label(self):
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(AllGenresFilter, request)

        assert filter_instance.get_options(q="fic") == [
            ("fiction", "Fiction"),
            ("nonfiction", "Non-fiction"),
        ]

    def test_queryset_filters_by_selected_genre(self):
        Book.objects.create(title="Dune", genre="fiction")
        Book.objects.create(title="Cosmos", genre="nonfiction")

        request = RequestFactory().get("/admin/tests/book/", {"genre": "fiction"})
        filter_instance = self._build_filter(
            GenreFilter, request, {"genre": ["fiction"]}
        )

        result = filter_instance.queryset(request, Book.objects.all())

        assert list(result.values_list("title", flat=True)) == ["Dune"]

    def test_get_async_options_lists_all_and_selected(self):
        Book.objects.create(title="Dune", genre="fiction")

        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(GenreFilter, request)

        options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")

        assert options == [
            (filter_instance.all_value, "All"),
            ("fiction", "Fiction"),
        ]

    def test_sync_lookups_return_used_options(self):
        Book.objects.create(title="Dune", genre="fiction")

        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(GenreFilter, request)

        assert filter_instance.lookups(request, admin.site._registry[Book]) == [
            ("fiction", "Fiction")
        ]

    def test_async_lookups_returns_empty_without_selection(self):
        request = RequestFactory().get("/admin/tests/book/")
        filter_instance = self._build_filter(AsyncGenreFilter, request)

        assert filter_instance.lookups(request, admin.site._registry[Book]) == []

    def test_async_lookups_returns_selected_option(self):
        request = RequestFactory().get("/admin/tests/book/", {"genre": "fiction"})
        filter_instance = self._build_filter(
            AsyncGenreFilter, request, {"genre": ["fiction"]}
        )

        assert filter_instance.lookups(request, admin.site._registry[Book]) == [
            ("fiction", "Fiction")
        ]
