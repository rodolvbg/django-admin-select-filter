import re
from unittest.mock import patch

import django
import pytest
from django.contrib import admin
from django.contrib.admin.filters import SimpleListFilter
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from django_admin_select_filter.filters import (
    BaseSelectFilter,
    ChoiceFilter,
    ForeignKeyFilter,
    field_list_filter,
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
    MultipleAsyncAuthorFilter,
    MultipleAsyncGenreFilter,
    MultipleAuthorFilter,
    MultipleGenreFilter,
    NonRelationChainFilter,
    NonSearchableGenreFilter,
    OnlyNameAuthorFilter,
    UnknownChainFilter,
)
from tests.testapp.models import Author, Book, Country

pytestmark = pytest.mark.django_db


def _changelist_params(params):
    """Adapt a ``{name: [value, ...]}`` params dict — the shape every
    filter construction in this file uses — to whatever shape Django's
    own ``ChangeList`` actually passes to a list filter's constructor
    for the installed Django version: a list per key
    (``request.GET.lists()``) from Django 5.0 on, a single scalar value
    per key (``request.GET.items()``) before that.
    """
    if not params:
        return {}
    if django.VERSION >= (5, 0):
        return {
            key: value if isinstance(value, list) else [value]
            for key, value in params.items()
        }
    return {
        key: value[-1] if isinstance(value, list) else value
        for key, value in params.items()
    }


@pytest.fixture(autouse=True)
def _adapt_filter_params_to_django_version(monkeypatch):
    """Every filter construction in this file passes ``params`` shaped
    for Django 5.0+ (a list of raw values per key). Real Django < 5.0
    builds a single scalar per key instead — the filter classes under
    test never build this dict themselves, they only read
    ``self.used_parameters``, which ``SimpleListFilter.__init__``
    populates from whatever shape ``params`` arrives in. Patching that
    one shared choke point (rather than every one of this file's ~20
    call sites) adapts every filter construction transparently, so
    tests don't silently return empty querysets on Django < 5.0 instead
    of exercising the real behavior.
    """
    original_init = SimpleListFilter.__init__

    def patched_init(self, request, params, model, model_admin):
        original_init(self, request, _changelist_params(params), model, model_admin)

    monkeypatch.setattr(SimpleListFilter, "__init__", patched_init)


class _FakeChangeList:
    add_facets = False

    def get_query_string(self, new_params=None, remove=None):
        return "?author=1"


class _FakeModelAdmin:
    def __init__(self, queryset):
        self.queryset = queryset
        self.calls = 0

    def get_queryset(self, request):
        self.calls += 1
        return self.queryset


class TestBaseSelectFilter:
    """The shared base: configuration, options, queryset and media."""

    def _build(self, **attrs):
        filter_instance = BaseSelectFilter.__new__(BaseSelectFilter)
        defaults = {
            "all_value": "__all__",
            "null_value": "__null__",
            "filter_only_used_values": True,
            "async_call": False,
            "nullable": None,
            "parameter_name": None,
            "used_parameters": {},
            **attrs,
        }
        for name, value in defaults.items():
            setattr(filter_instance, name, value)
        return filter_instance

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

    def test_model_admin_queryset_caches_the_admin_queryset(self):
        model_admin = _FakeModelAdmin(Book.objects.all())
        filter_instance = self._build(
            model_admin=model_admin, request=RequestFactory().get("/admin/")
        )

        first = filter_instance.model_admin_queryset
        second = filter_instance.model_admin_queryset

        assert first is second
        assert model_admin.calls == 1

    @pytest.mark.parametrize(
        ("parameter_name", "expected"),
        [
            ("author", True),
            ("title", False),
            ("author_id", True),
            ("does_not_exist", False),
        ],
        ids=[
            "nullable field matched by name",
            "non-nullable field matched by name",
            "nullable field matched by attname",
            "field that doesn't exist",
        ],
    )
    def test__is_nullable(self, parameter_name, expected):
        filter_instance = self._build()
        filter_instance.parameter_name = parameter_name
        assert filter_instance._is_nullable(Book) is expected

    def test__has_null_option_not_nullable(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author, genre="fiction")
        orphan_queryset = _FakeModelAdmin(Book.objects.filter(author=None))
        request = RequestFactory().get("/admin/")

        filter_instance = self._build(
            nullable=False,
            parameter_name="author",
            model_admin=orphan_queryset,
            request=request,
        )
        assert not filter_instance._has_null_option()

    def test__has_null_option_nullable_but_no_parameter_name(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author, genre="fiction")
        orphan_queryset = _FakeModelAdmin(Book.objects.filter(author=None))
        request = RequestFactory().get("/admin/")

        filter_instance = self._build(
            nullable=True,
            parameter_name=None,
            model_admin=orphan_queryset,
            request=request,
        )
        assert not filter_instance._has_null_option()

    def test__has_null_option_nullable_all_values_shown(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author, genre="fiction")
        populated_queryset = _FakeModelAdmin(Book.objects.filter(author=author))
        request = RequestFactory().get("/admin/")

        filter_instance = self._build(
            nullable=True,
            parameter_name="author",
            filter_only_used_values=False,
            model_admin=populated_queryset,
            request=request,
        )
        assert filter_instance._has_null_option()

    def test__has_null_option_used_values_only_null_row_exists(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author, genre="fiction")
        orphan_queryset = _FakeModelAdmin(Book.objects.filter(author=None))
        request = RequestFactory().get("/admin/")

        Book.objects.create(title="Orphan", author=None)
        filter_instance = self._build(
            nullable=True,
            parameter_name="author",
            filter_only_used_values=True,
            model_admin=orphan_queryset,
            request=request,
        )
        assert filter_instance._has_null_option()

    def test__has_null_option_used_values_only_no_null_row(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author, genre="fiction")
        populated_queryset = _FakeModelAdmin(Book.objects.filter(author=author))
        request = RequestFactory().get("/admin/")

        filter_instance = self._build(
            nullable=True,
            parameter_name="author",
            filter_only_used_values=True,
            model_admin=populated_queryset,
            request=request,
        )
        assert not filter_instance._has_null_option()

    @pytest.mark.parametrize(
        ("parameter_name", "expected_name"),
        [
            (None, None),
            ("author", "author"),
            ("does_not_exist", None),
            ("author__country", "country"),
            ("bogus__country", None),
            ("title__country", None),
            ("author__does_not_exist", None),
        ],
        ids=[
            "no parameter_name",
            "single segment, valid field",
            "single segment, unknown field",
            "nested, valid relation chain",
            "nested, unknown middle segment",
            "nested, non-relation middle segment",
            "nested, unknown final segment",
        ],
    )
    def test__resolve_field(self, parameter_name, expected_name):
        filter_instance = self._build()
        filter_instance.parameter_name = parameter_name

        field = filter_instance._resolve_field(Book)

        assert (field.name if field is not None else None) == expected_name

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

    def test__build_async_options_multiple_skips_the_all_option(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        Book.objects.create(title="Orphan", author=None)
        model_admin = admin.site._registry[Book]
        items = [(str(author.pk), "Rowling")]

        filter_instance = self._build(
            nullable=False,
            parameter_name="author",
            multiple=True,
            model_admin=model_admin,
            request=RequestFactory().get("/admin/"),
        )
        options = filter_instance._build_async_options(
            RequestFactory().get("/api/"), items
        )
        assert options == items

    def test_has_output_async_filter_always_has_output(self):
        filter_instance = self._build(async_call=True, lookup_choices=[])
        assert filter_instance.has_output()

    def test_has_output_sync_filter_with_lookup_choices(self):
        filter_instance = self._build(async_call=False, lookup_choices=[("a", "A")])
        assert filter_instance.has_output()

    def test_has_output_sync_filter_without_lookup_choices(self):
        filter_instance = self._build(async_call=False, lookup_choices=[])
        assert not filter_instance.has_output()

    def test_selected_values_nothing_selected(self):
        filter_instance = self._build(parameter_name="x", used_parameters={})
        assert filter_instance.selected_values() == []

    def test_selected_values_single_mode_returns_the_raw_value_as_is(self):
        filter_instance = self._build(parameter_name="x", used_parameters={"x": "a,b"})
        assert filter_instance.selected_values() == ["a,b"]

    def test_selected_values_multiple_mode_splits_on_the_separator(self):
        filter_instance = self._build(
            parameter_name="x", used_parameters={"x": "a,b"}, multiple=True
        )
        assert filter_instance.selected_values() == ["a", "b"]

    def test_selected_values_multiple_mode_drops_empty_segments(self):
        filter_instance = self._build(
            parameter_name="x", used_parameters={"x": "a,,b,"}, multiple=True
        )
        assert filter_instance.selected_values() == ["a", "b"]

    def test_queryset_no_value_selected(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(parameter_name="author", used_parameters={})
        assert filter_instance.queryset(request, all_books) is all_books

    def test_queryset_no_parameter_name_configured(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name=None, used_parameters={"author": str(author.pk)}
        )
        assert filter_instance.queryset(request, all_books) is all_books

    def test_queryset_null_value_filters_null_relations(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name="author", used_parameters={"author": "__null__"}
        )
        result = filter_instance.queryset(request, all_books)
        assert list(result.values_list("title", flat=True)) == ["Orphan"]

    def test_queryset_regular_value_filters_by_lookup(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name="author",
            used_parameters={"author": str(author.pk)},
        )
        result = filter_instance.queryset(request, all_books)
        assert list(result.values_list("title", flat=True)) == ["HP"]

    def test_queryset_multiple_values_filter_with_in(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name="author",
            used_parameters={"author": f"{author.pk},{tolkien.pk}"},
            multiple=True,
        )
        result = filter_instance.queryset(request, all_books)
        assert set(result.values_list("title", flat=True)) == {"HP", "LOTR"}

    def test_queryset_multiple_values_combine_in_with_the_null_lookup(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name="author",
            used_parameters={"author": f"{author.pk},__null__"},
            multiple=True,
        )
        result = filter_instance.queryset(request, all_books)
        assert set(result.values_list("title", flat=True)) == {"HP", "Orphan"}

    def test_queryset_multiple_with_only_the_null_value_selected(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name="author",
            used_parameters={"author": "__null__"},
            multiple=True,
        )
        result = filter_instance.queryset(request, all_books)
        assert list(result.values_list("title", flat=True)) == ["Orphan"]

    def test_select2_theme_is_select2_default_without_unfold(self):
        filter_instance = self._build()
        assert filter_instance.select2_theme is None
        assert "autocomplete.css" not in str(filter_instance.media["css"])

    def test_select2_theme_is_the_admin_autocomplete_theme_with_unfold(self):
        from unittest import mock

        with mock.patch(
            "django_admin_select_filter.filters.apps.is_installed",
            side_effect=lambda app: app == "unfold",
        ):
            filter_instance = self._build()
            assert filter_instance.select2_theme == "admin-autocomplete"
            css_html = str(filter_instance.media["css"])
        assert 'href="/static/admin/css/autocomplete.css"' in css_html
        assert css_html.index("select2.css") < css_html.index("autocomplete.css")

    def test_select2_theme_explicit_theme_wins(self):
        filter_instance = self._build(theme="classic")
        assert filter_instance.select2_theme == "classic"

    def test_media_css_is_always_the_same(self):
        filter_instance = self._build()
        css_html = str(filter_instance.media["css"])
        assert 'href="/static/admin/css/vendor/select2/select2.css"' in css_html
        assert (
            'href="/static/admin_select_filter/css/admin_select2_filter.css"'
            in css_html
        )

    def test_media_sync_searchable_single_has_core_js_only(self):
        filter_instance = self._build(async_call=False, searchable=True, multiple=False)
        js_html = str(filter_instance.media["js"])
        assert js_html == (
            '<script type="module"'
            ' src="/static/admin_select_filter/js/core.js"></script>'
        )
        assert "async_options.js" not in js_html
        assert "non_searchable.js" not in js_html
        assert "multiple_navigation.js" not in js_html

    def test_media_async_call_adds_async_options_js(self):
        filter_instance = self._build(async_call=True)
        assert "admin_select_filter/js/async_options.js" in str(
            filter_instance.media["js"]
        )

    def test_media_searchable_false_adds_non_searchable_js(self):
        filter_instance = self._build(searchable=False)
        assert "admin_select_filter/js/non_searchable.js" in str(
            filter_instance.media["js"]
        )

    def test_media_multiple_adds_multiple_navigation_js(self):
        filter_instance = self._build(multiple=True)
        assert "admin_select_filter/js/multiple_navigation.js" in str(
            filter_instance.media["js"]
        )

    def test_media_every_capability_combined_in_a_fixed_order(self):
        filter_instance = self._build(async_call=True, searchable=False, multiple=True)
        js_html = str(filter_instance.media["js"])
        names = [
            "core.js",
            "async_options.js",
            "non_searchable.js",
            "multiple_navigation.js",
        ]
        positions = [js_html.index(name) for name in names]
        assert positions == sorted(positions)
        assert js_html.count("<script") == 4
        # Nothing inline for a Content Security Policy to block.
        assert js_html.count("<script") == js_html.count(" src=")
        assert "importmap" not in js_html

    def test_media_without_request_attribute_has_no_nonce_and_no_crash(self):
        filter_instance = self._build()
        assert "nonce" not in str(filter_instance.media["js"])

    def test_media_request_without_csp_nonce_has_no_nonce(self):
        filter_instance = self._build(request=RequestFactory().get("/admin/"))
        assert "nonce" not in str(filter_instance.media["js"])

    def test_media_csp_nonce_picked_up_from_the_request(self):
        request = RequestFactory().get("/admin/")
        setattr(request, "csp_nonce", "abc123")  # noqa: B010
        filter_instance = self._build(request=request)
        js_html = str(filter_instance.media["js"])
        assert js_html.count('nonce="abc123"') == 1

    def test_media_picks_up_djangos_csp_middleware_nonce(self):
        request = RequestFactory().get("/admin/")
        setattr(request, "_csp_nonce", "def456")  # noqa: B010
        filter_instance = self._build(request=request, multiple=True)
        js_html = str(filter_instance.media["js"])
        assert js_html.count('nonce="def456"') == 2

    def test_choices_single_selection(self):
        filter_instance = self._build(
            parameter_name="x",
            used_parameters={},
            lookup_choices=[("a", "Label A"), ("b", "Label B")],
        )
        choices = list(filter_instance.choices(_FakeChangeList()))
        assert [choice["key"] for choice in choices] == ["", "a", "b"]
        assert [choice["display"] for choice in choices] == [
            "All",
            "Label A",
            "Label B",
        ]
        assert choices[0]["selected"]
        assert not choices[1]["selected"]
        assert not choices[2]["selected"]

    def test_choices_multiple_selection_marks_every_selected_key(self):
        filter_instance = self._build(
            parameter_name="x",
            used_parameters={"x": "a,b"},
            multiple=True,
            lookup_choices=[("a", "Label A"), ("b", "Label B"), ("c", "Label C")],
        )
        choices = list(filter_instance.choices(_FakeChangeList()))
        assert [choice["selected"] for choice in choices] == [False, True, True, False]

    def test_option_items_is_abstract(self):
        filter_instance = self._build()
        with pytest.raises(NotImplementedError):
            filter_instance._option_items()

    def test_selected_option_items_is_abstract(self):
        filter_instance = self._build()
        with pytest.raises(NotImplementedError):
            filter_instance._selected_option_items()

    def test_get_async_options_requires_option_items(
        self,
    ):
        filter_instance = self._build()
        with pytest.raises(NotImplementedError):
            filter_instance.get_async_options(RequestFactory().get("/api/"), "")

    def test_lookups_requires_option_items_when_not_async(
        self,
    ):
        filter_instance = self._build(async_call=False)
        with pytest.raises(NotImplementedError):
            filter_instance.lookups(RequestFactory().get("/admin/"), None)

    def test_lookups_requires_selected_option_items_when_async(
        self,
    ):
        filter_instance = self._build(async_call=True)
        with pytest.raises(NotImplementedError):
            filter_instance.lookups(RequestFactory().get("/admin/"), None)

    def test_get_async_options_delegates_to_option_items(self):
        filter_instance = self._build(
            nullable=False,
            parameter_name="x",
            _option_items=lambda request=None, q="": [("1", "One")],
        )
        options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")
        assert options == [(filter_instance.all_value, "All"), ("1", "One")]

    def test_lookups_in_sync_mode_uses_option_items(
        self,
    ):
        filter_instance = self._build(
            async_call=False,
            has_null_option=False,
            _option_items=lambda request=None, q="": [("1", "One")],
            _selected_option_items=lambda: [],
        )
        result = filter_instance.lookups(RequestFactory().get("/admin/"), None)
        assert result == [("1", "One")]

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

    def test_lookups_appends_the_null_option_when_present(
        self,
    ):
        filter_instance = self._build(
            async_call=False,
            has_null_option=True,
            _option_items=lambda request=None, q="": [("1", "One")],
        )
        result = filter_instance.lookups(RequestFactory().get("/admin/"), None)
        assert result == [("1", "One"), (filter_instance.null_value, "-")]


class TestForeignKeyFilter:
    """The foreign-key flavour: model inference, options and rendering."""

    def _build_filter(self, request, params=None):
        model_admin = admin.site._registry[Book]
        return AuthorFilter(request, params or {}, Book, model_admin)

    @pytest.mark.parametrize(
        ("parameter_name", "expected"),
        [
            (None, None),
            ("does_not_exist", None),
            ("author", Author),
            ("author__country", Country),
            ("title", None),
        ],
        ids=[
            "no parameter_name",
            "unknown field",
            "plain relation field",
            "nested relation chain",
            "final segment isn't a relation",
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


class TestChoiceFilter:
    """The choices flavour: options from field choices or explicit ones."""

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


class TestFieldListFilter:
    """The field_list_filter factory for the (field, filter) tuple form."""

    """Tests for the ``list_filter = [("field", field_list_filter(...))]`` form."""

    def _resolved_field(self, model, field_path):
        for part in field_path.split("__")[:-1]:
            model = model._meta.get_field(part).related_model
        return model._meta.get_field(field_path.rsplit("__", 1)[-1])

    def test_produces_bound_instance_inferring_parameter_name_from_field_path(
        self,
    ):
        author = Author.objects.create(name="Rowling")
        country = Country.objects.create(name="UK")
        author.country = country
        author.save()
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = self._resolved_field(Book, "author__country")
        factory = field_list_filter(ForeignKeyFilter)
        filter_instance = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )

        assert filter_instance.parameter_name == "author__country"

    def test_produces_bound_instance_inferring_model_from_nested_lookup(
        self,
    ):
        author = Author.objects.create(name="Rowling")
        country = Country.objects.create(name="UK")
        author.country = country
        author.save()
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = self._resolved_field(Book, "author__country")
        factory = field_list_filter(ForeignKeyFilter)
        filter_instance = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )

        assert filter_instance.model is Country

    def test_produces_bound_instance_behaving_like_a_foreign_key_filter(
        self,
    ):
        author = Author.objects.create(name="Rowling")
        country = Country.objects.create(name="UK")
        author.country = country
        author.save()
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = self._resolved_field(Book, "author__country")
        factory = field_list_filter(ForeignKeyFilter)
        filter_instance = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )

        assert list(filter_instance.get_options()) == [country]

    def test_falls_back_to_field_name_without_field_path(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = Book._meta.get_field("genre")

        factory = field_list_filter(ChoiceFilter)
        filter_instance = factory(field, request, {}, Book, model_admin)

        assert filter_instance.parameter_name == "genre"

    def test_reuses_the_same_bound_class_across_calls(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = self._resolved_field(Book, "author__country")
        factory = field_list_filter(ForeignKeyFilter)

        first = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )
        second = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )

        assert type(first) is type(second)

    def test_rejects_an_async_call_filter(self):
        class AsyncFK(ForeignKeyFilter):
            async_call = True

        with pytest.raises(TypeError, match="doesn't support async_call"):
            field_list_filter(AsyncFK)

    def test_changelist_renders_the_tuple_form_filter(self):
        """End-to-end: BookAdmin.list_filter includes
        ``("author__country", field_list_filter(ForeignKeyFilter))``; make
        sure Django's own ChangeList machinery accepts it, not just a direct
        call to the factory.
        """
        author = Author.objects.create(name="Rowling")
        country = Country.objects.create(name="UK")
        author.country = country
        author.save()
        Book.objects.create(title="HP", author=author)

        request = RequestFactory().get("/admin/tests/book/")
        request.user = User.objects.create_superuser(
            "field_list_filter_admin", "flf@example.com", "password"
        )
        model_admin = admin.site._registry[Book]
        filter_specs, *_ = model_admin.get_changelist_instance(request).get_filters(
            request
        )
        matching = [
            spec
            for spec in filter_specs
            if isinstance(spec, ForeignKeyFilter)
            and spec.parameter_name == "author__country"
        ]

        assert len(matching) == 1
        assert list(matching[0].get_options()) == [country]


def test_choices_type_alias_is_importable():
    # Only imported under TYPE_CHECKING by the package itself.
    from django_admin_select_filter.types import Choices

    assert Choices == list[tuple[str, str]]
