import pytest
from django.contrib import admin
from django.template.loader import render_to_string
from django.test import RequestFactory

from django_admin_select_filter.filters import ChoiceFilter, ForeignKeyFilter
from tests.testapp.admin import (
    AllGenresFilter,
    AllNullableAuthorFilter,
    AsyncAuthorFilter,
    AsyncGenreFilter,
    AuthorFilter,
    ExplicitNullableAuthorFilter,
    ExplicitOptionsGenreFilter,
    FixedTitleAuthorFilter,
    GenreFilter,
    MissingFieldFilter,
    OnlyNameAuthorFilter,
)
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db


def _build_filter(request, params=None):
    model_admin = admin.site._registry[Book]
    return AuthorFilter(request, params or {}, Book, model_admin)


def test_queryset_filters_by_selected_author():
    factory = RequestFactory()
    rowling = Author.objects.create(name="Rowling")
    tolkien = Author.objects.create(name="Tolkien")
    Book.objects.create(title="Harry Potter", author=rowling)
    Book.objects.create(title="The Hobbit", author=tolkien)

    request = factory.get("/admin/tests/book/", {"author": str(rowling.pk)})
    filter_instance = _build_filter(request, {"author": [str(rowling.pk)]})

    result = filter_instance.queryset(request, Book.objects.all())

    assert list(result.values_list("title", flat=True)) == ["Harry Potter"]


def test_get_options_only_returns_used_authors():
    factory = RequestFactory()
    used = Author.objects.create(name="Used")
    Author.objects.create(name="Unused")
    Book.objects.create(title="A Book", author=used)

    request = factory.get("/admin/tests/book/")
    filter_instance = _build_filter(request)

    assert list(filter_instance.get_options()) == [used]


def test_null_option_present_when_null_books_exist():
    factory = RequestFactory()
    Book.objects.create(title="Orphan Book", author=None)

    request = factory.get("/admin/tests/book/")
    filter_instance = _build_filter(request)

    assert filter_instance.has_null_option is True


class _FakeChangeList:
    add_facets = False

    def get_query_string(self, new_params=None, remove=None):
        return "?author=1"


def test_template_renders_select2_markup():
    factory = RequestFactory()
    author = Author.objects.create(name="Rowling")
    Book.objects.create(title="Harry Potter", author=author)

    request = factory.get("/admin/tests/book/")
    filter_instance = _build_filter(request)

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


def test_missing_model_is_rejected():
    class InvalidFilter(ForeignKeyFilter):
        parameter_name = "author"

    with pytest.raises(TypeError, match="model must be configured"):
        InvalidFilter(
            RequestFactory().get("/admin/"), {}, Book, admin.site._registry[Book]
        )


def test_explicit_title_skips_default_lookup():
    request = RequestFactory().get("/admin/")
    filter_instance = FixedTitleAuthorFilter(
        request, {}, Book, admin.site._registry[Book]
    )

    assert filter_instance.title == "Fixed title"


def test_explicit_nullable_skips_field_inference():
    request = RequestFactory().get("/admin/")
    filter_instance = ExplicitNullableAuthorFilter(
        request, {}, Book, admin.site._registry[Book]
    )

    assert filter_instance.nullable is False
    assert filter_instance.has_null_option is False


def test_missing_field_is_not_nullable():
    request = RequestFactory().get("/admin/")
    filter_instance = MissingFieldFilter(request, {}, Book, admin.site._registry[Book])

    assert filter_instance.nullable is False
    assert filter_instance.has_null_option is False


def test_filter_only_used_values_false_always_shows_null_option():
    request = RequestFactory().get("/admin/")
    filter_instance = AllNullableAuthorFilter(
        request, {}, Book, admin.site._registry[Book]
    )

    assert filter_instance.has_null_option is True


def test_get_options_without_used_filter_returns_all_authors():
    unused = Author.objects.create(name="Unused")

    request = RequestFactory().get("/admin/")
    filter_instance = AllNullableAuthorFilter(
        request, {}, Book, admin.site._registry[Book]
    )

    assert list(filter_instance.get_options()) == [unused]


def test_get_options_respects_only_fields():
    author = Author.objects.create(name="Solo")
    Book.objects.create(title="Book", author=author)

    request = RequestFactory().get("/admin/")
    filter_instance = OnlyNameAuthorFilter(
        request, {}, Book, admin.site._registry[Book]
    )

    assert list(filter_instance.get_options()) == [author]


def test_get_options_searches_related_admin():
    match = Author.objects.create(name="Rowling")
    Author.objects.create(name="Tolkien")
    Book.objects.create(title="HP", author=match)
    Book.objects.create(title="LOTR", author=Author.objects.get(name="Tolkien"))

    request = RequestFactory().get("/admin/")
    filter_instance = _build_filter(request)

    assert list(filter_instance.get_options(q="Rowl")) == [match]


def test_get_options_deduplicates_when_related_admin_reports_duplicates(monkeypatch):
    author = Author.objects.create(name="Rowling")
    Book.objects.create(title="HP", author=author)
    related_admin = admin.site._registry[Author]
    monkeypatch.setattr(
        related_admin,
        "get_search_results",
        lambda request, queryset, term: (queryset, True),
    )

    request = RequestFactory().get("/admin/")
    filter_instance = _build_filter(request)

    assert list(filter_instance.get_options(q="anything")) == [author]


def test_get_async_options_lists_all_and_selected():
    author = Author.objects.create(name="Rowling")
    Book.objects.create(title="HP", author=author)

    request = RequestFactory().get("/admin/")
    filter_instance = _build_filter(request)

    options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")

    assert options == [
        (filter_instance.all_value, "All"),
        (str(author.pk), "Rowling"),
    ]


def test_get_async_options_includes_null_value():
    request = RequestFactory().get("/admin/")
    filter_instance = AllNullableAuthorFilter(
        request, {}, Book, admin.site._registry[Book]
    )

    options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")

    assert options[-1] == (filter_instance.null_value, "-")


def test_get_async_options_applies_facet_counts():
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


def test_missing_parameter_name_short_circuits_facet_counts_and_queryset():
    filter_instance = ForeignKeyFilter.__new__(ForeignKeyFilter)
    filter_instance.used_parameters = {}
    queryset = Book.objects.all()

    assert filter_instance._get_option_facet_counts() == {}
    assert (
        filter_instance.queryset(RequestFactory().get("/admin/"), queryset) is queryset
    )


def test_queryset_without_selected_value_is_unchanged():
    request = RequestFactory().get("/admin/tests/book/")
    filter_instance = _build_filter(request)
    queryset = Book.objects.all()

    assert filter_instance.queryset(request, queryset) is queryset


def test_queryset_null_value_filters_null_relations():
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


def test_async_lookups_returns_empty_without_selection():
    request = RequestFactory().get("/admin/tests/book/")
    filter_instance = AsyncAuthorFilter(request, {}, Book, admin.site._registry[Book])

    assert filter_instance.lookups(request, admin.site._registry[Book]) == []


def test_async_lookups_returns_selected_instance():
    author = Author.objects.create(name="Rowling")

    request = RequestFactory().get("/admin/tests/book/", {"author": str(author.pk)})
    filter_instance = AsyncAuthorFilter(
        request, {"author": [str(author.pk)]}, Book, admin.site._registry[Book]
    )

    assert filter_instance.lookups(request, admin.site._registry[Book]) == [
        (str(author.pk), "Rowling")
    ]


def test_has_output_true_for_async_filter_without_options():
    request = RequestFactory().get("/admin/tests/book/")
    filter_instance = AsyncAuthorFilter(request, {}, Book, admin.site._registry[Book])

    assert filter_instance.has_output() is True


def test_has_output_false_when_no_options_available():
    request = RequestFactory().get("/admin/tests/book/")
    filter_instance = _build_filter(request)

    assert filter_instance.has_output() is False


def _build_genre_filter(filter_class, request, params=None):
    model_admin = admin.site._registry[Book]
    return filter_class(request, params or {}, Book, model_admin)


def test_choice_filter_derives_options_from_field_choices():
    request = RequestFactory().get("/admin/")
    filter_instance = _build_genre_filter(AllGenresFilter, request)

    assert filter_instance.options == [
        ("fiction", "Fiction"),
        ("nonfiction", "Non-fiction"),
        ("poetry", "Poetry"),
    ]
    assert filter_instance.title == "genre"


def test_choice_filter_requires_parameter_name():
    class InvalidFilter(ChoiceFilter):
        pass

    with pytest.raises(TypeError, match="parameter_name must be configured"):
        InvalidFilter(
            RequestFactory().get("/admin/"), {}, Book, admin.site._registry[Book]
        )


def test_choice_filter_requires_options_or_field_choices():
    class InvalidFilter(ChoiceFilter):
        parameter_name = "title"

    with pytest.raises(TypeError, match="options must be configured"):
        InvalidFilter(
            RequestFactory().get("/admin/"), {}, Book, admin.site._registry[Book]
        )


def test_choice_filter_accepts_explicit_options():
    request = RequestFactory().get("/admin/")
    filter_instance = _build_genre_filter(ExplicitOptionsGenreFilter, request)

    assert filter_instance.options == [("fiction", "Fiction"), ("poetry", "Poetry")]


def test_choice_filter_get_options_only_returns_used_values():
    Book.objects.create(title="Dune", genre="fiction")

    request = RequestFactory().get("/admin/")
    filter_instance = _build_genre_filter(GenreFilter, request)

    assert filter_instance.get_options() == [("fiction", "Fiction")]


def test_choice_filter_get_options_without_used_filter_returns_all():
    request = RequestFactory().get("/admin/")
    filter_instance = _build_genre_filter(AllGenresFilter, request)

    assert filter_instance.get_options() == [
        ("fiction", "Fiction"),
        ("nonfiction", "Non-fiction"),
        ("poetry", "Poetry"),
    ]


def test_choice_filter_get_options_searches_by_label():
    request = RequestFactory().get("/admin/")
    filter_instance = _build_genre_filter(AllGenresFilter, request)

    assert filter_instance.get_options(q="fic") == [
        ("fiction", "Fiction"),
        ("nonfiction", "Non-fiction"),
    ]


def test_choice_filter_queryset_filters_by_selected_genre():
    Book.objects.create(title="Dune", genre="fiction")
    Book.objects.create(title="Cosmos", genre="nonfiction")

    request = RequestFactory().get("/admin/tests/book/", {"genre": "fiction"})
    filter_instance = _build_genre_filter(GenreFilter, request, {"genre": ["fiction"]})

    result = filter_instance.queryset(request, Book.objects.all())

    assert list(result.values_list("title", flat=True)) == ["Dune"]


def test_choice_filter_get_async_options_lists_all_and_selected():
    Book.objects.create(title="Dune", genre="fiction")

    request = RequestFactory().get("/admin/")
    filter_instance = _build_genre_filter(GenreFilter, request)

    options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")

    assert options == [
        (filter_instance.all_value, "All"),
        ("fiction", "Fiction"),
    ]


def test_choice_filter_sync_lookups_return_used_options():
    Book.objects.create(title="Dune", genre="fiction")

    request = RequestFactory().get("/admin/")
    filter_instance = _build_genre_filter(GenreFilter, request)

    assert filter_instance.lookups(request, admin.site._registry[Book]) == [
        ("fiction", "Fiction")
    ]


def test_choice_filter_async_lookups_returns_empty_without_selection():
    request = RequestFactory().get("/admin/tests/book/")
    filter_instance = _build_genre_filter(AsyncGenreFilter, request)

    assert filter_instance.lookups(request, admin.site._registry[Book]) == []


def test_choice_filter_async_lookups_returns_selected_option():
    request = RequestFactory().get("/admin/tests/book/", {"genre": "fiction"})
    filter_instance = _build_genre_filter(
        AsyncGenreFilter, request, {"genre": ["fiction"]}
    )

    assert filter_instance.lookups(request, admin.site._registry[Book]) == [
        ("fiction", "Fiction")
    ]
