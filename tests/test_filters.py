import re
from unittest.mock import patch

import django
import pytest
from django.contrib import admin
from django.contrib.admin.filters import SimpleListFilter
from django.contrib.auth.models import User
from django.db import transaction
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
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


class BaseSelectFilterTests(TestCase):
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

    def test_async_call_url(self):
        with self.subTest("class default is None"):
            self.assertIsNone(BaseSelectFilter.async_call_url)

        with self.subTest("resolved via reverse() when async and unset"):
            request = RequestFactory().get("/admin/")
            filter_instance: BaseSelectFilter = AsyncAuthorFilter(
                request, {}, Book, admin.site._registry[Book]
            )
            self.assertEqual(
                filter_instance.async_call_url,
                reverse("admin_select_filter:options"),
            )

        with self.subTest("left as None when not async"):
            request = RequestFactory().get("/admin/")
            filter_instance = AuthorFilter(
                request, {}, Book, admin.site._registry[Book]
            )
            self.assertIsNone(filter_instance.async_call_url)

        with self.subTest("explicit override is preserved"):

            class CustomAsyncFilter(AsyncAuthorFilter):
                async_call_url = "/custom/options/"

            request = RequestFactory().get("/admin/")
            filter_instance = CustomAsyncFilter(
                request, {}, Book, admin.site._registry[Book]
            )
            self.assertEqual(filter_instance.async_call_url, "/custom/options/")

    def test_model_admin_queryset_caches_the_admin_queryset(self):
        model_admin = _FakeModelAdmin(Book.objects.all())
        filter_instance = self._build(
            model_admin=model_admin, request=RequestFactory().get("/admin/")
        )

        first = filter_instance.model_admin_queryset
        second = filter_instance.model_admin_queryset

        self.assertIs(first, second)
        self.assertEqual(model_admin.calls, 1)

    def test__is_nullable(self):
        cases = {
            "nullable field matched by name": ("author", True),
            "non-nullable field matched by name": ("title", False),
            "nullable field matched by attname": ("author_id", True),
            "field that doesn't exist": ("does_not_exist", False),
        }
        filter_instance = self._build()
        for description, (parameter_name, expected) in cases.items():
            with self.subTest(description):
                filter_instance.parameter_name = parameter_name
                self.assertIs(filter_instance._is_nullable(Book), expected)

    def test__has_null_option(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author, genre="fiction")
        orphan_queryset = _FakeModelAdmin(Book.objects.filter(author=None))
        populated_queryset = _FakeModelAdmin(Book.objects.filter(author=author))
        request = RequestFactory().get("/admin/")

        with self.subTest("not nullable"):
            filter_instance = self._build(
                nullable=False,
                parameter_name="author",
                model_admin=orphan_queryset,
                request=request,
            )
            self.assertFalse(filter_instance._has_null_option())

        with self.subTest("nullable but no parameter_name"):
            filter_instance = self._build(
                nullable=True,
                parameter_name=None,
                model_admin=orphan_queryset,
                request=request,
            )
            self.assertFalse(filter_instance._has_null_option())

        with self.subTest("nullable, all values shown regardless of usage"):
            filter_instance = self._build(
                nullable=True,
                parameter_name="author",
                filter_only_used_values=False,
                model_admin=populated_queryset,
                request=request,
            )
            self.assertTrue(filter_instance._has_null_option())

        with self.subTest("nullable, used values only, null row exists"):
            Book.objects.create(title="Orphan", author=None)
            filter_instance = self._build(
                nullable=True,
                parameter_name="author",
                filter_only_used_values=True,
                model_admin=orphan_queryset,
                request=request,
            )
            self.assertTrue(filter_instance._has_null_option())

        with self.subTest("nullable, used values only, no null row"):
            filter_instance = self._build(
                nullable=True,
                parameter_name="author",
                filter_only_used_values=True,
                model_admin=populated_queryset,
                request=request,
            )
            self.assertFalse(filter_instance._has_null_option())

    def test__resolve_field(self):
        filter_instance = self._build()

        with self.subTest("no parameter_name"):
            filter_instance.parameter_name = None
            self.assertIsNone(filter_instance._resolve_field(Book))

        with self.subTest("single segment, valid field"):
            filter_instance.parameter_name = "author"
            field = filter_instance._resolve_field(Book)
            assert field is not None
            self.assertEqual(field.name, "author")

        with self.subTest("single segment, unknown field"):
            filter_instance.parameter_name = "does_not_exist"
            self.assertIsNone(filter_instance._resolve_field(Book))

        with self.subTest("nested, valid relation chain"):
            filter_instance.parameter_name = "author__country"
            field = filter_instance._resolve_field(Book)
            assert field is not None
            self.assertEqual(field.name, "country")

        with self.subTest("nested, unknown middle segment"):
            filter_instance.parameter_name = "bogus__country"
            self.assertIsNone(filter_instance._resolve_field(Book))

        with self.subTest("nested, non-relation middle segment"):
            filter_instance.parameter_name = "title__country"
            self.assertIsNone(filter_instance._resolve_field(Book))

        with self.subTest("nested, unknown final segment"):
            filter_instance.parameter_name = "author__does_not_exist"
            self.assertIsNone(filter_instance._resolve_field(Book))

    def test__get_option_facet_counts(self):
        Book.objects.create(title="A", genre="fiction")
        Book.objects.create(title="B", genre="fiction")
        Book.objects.create(title="C", genre="poetry")
        Book.objects.create(title="D", genre=None)
        model_admin = admin.site._registry[Book]
        request = RequestFactory().get("/admin/")

        with self.subTest("no parameter_name"):
            filter_instance = self._build(
                parameter_name=None, model_admin=model_admin, request=request
            )
            self.assertEqual(filter_instance._get_option_facet_counts(), {})

        with self.subTest("grouped counts, including null"):
            filter_instance = self._build(
                parameter_name="genre", model_admin=model_admin, request=request
            )
            self.assertEqual(
                filter_instance._get_option_facet_counts(),
                {"fiction": 2, "poetry": 1, filter_instance.null_value: 1},
            )

    def test__build_async_options(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        Book.objects.create(title="Orphan", author=None)
        model_admin = admin.site._registry[Book]
        items = [(str(author.pk), "Rowling")]

        with self.subTest("plain, no null option, no facets"):
            filter_instance = self._build(
                nullable=False,
                parameter_name="author",
                model_admin=model_admin,
                request=RequestFactory().get("/admin/"),
            )
            options = filter_instance._build_async_options(
                RequestFactory().get("/api/"), items
            )
            self.assertEqual(options, [("__all__", "All"), *items])

        with self.subTest("null option appended"):
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
            self.assertEqual(options, [("__all__", "All"), *items, ("__null__", "-")])

        with self.subTest("facet counts applied to every non-All option"):
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
            self.assertEqual(
                options,
                [
                    ("__all__", "All"),
                    (str(author.pk), "Rowling (1)"),
                    ("__null__", "- (1)"),
                ],
            )

        with self.subTest("multiple skips the All option"):
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
            self.assertEqual(options, items)

    def test_has_output(self):
        with self.subTest("async filter always has output"):
            filter_instance = self._build(async_call=True, lookup_choices=[])
            self.assertTrue(filter_instance.has_output())

        with self.subTest("sync filter with lookup choices"):
            filter_instance = self._build(async_call=False, lookup_choices=[("a", "A")])
            self.assertTrue(filter_instance.has_output())

        with self.subTest("sync filter without lookup choices"):
            filter_instance = self._build(async_call=False, lookup_choices=[])
            self.assertFalse(filter_instance.has_output())

    def test_selected_values(self):
        with self.subTest("nothing selected"):
            filter_instance = self._build(parameter_name="x", used_parameters={})
            self.assertEqual(filter_instance.selected_values(), [])

        with self.subTest("single mode returns the raw value as-is"):
            filter_instance = self._build(
                parameter_name="x", used_parameters={"x": "a,b"}
            )
            self.assertEqual(filter_instance.selected_values(), ["a,b"])

        with self.subTest("multiple mode splits on the separator"):
            filter_instance = self._build(
                parameter_name="x", used_parameters={"x": "a,b"}, multiple=True
            )
            self.assertEqual(filter_instance.selected_values(), ["a", "b"])

        with self.subTest("multiple mode drops empty segments"):
            filter_instance = self._build(
                parameter_name="x", used_parameters={"x": "a,,b,"}, multiple=True
            )
            self.assertEqual(filter_instance.selected_values(), ["a", "b"])

    def test_queryset(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        with self.subTest("no value selected"):
            filter_instance = self._build(parameter_name="author", used_parameters={})
            self.assertIs(filter_instance.queryset(request, all_books), all_books)

        with self.subTest("no parameter_name configured"):
            filter_instance = self._build(
                parameter_name=None, used_parameters={"author": str(author.pk)}
            )
            self.assertIs(filter_instance.queryset(request, all_books), all_books)

        with self.subTest("null value filters null relations"):
            filter_instance = self._build(
                parameter_name="author", used_parameters={"author": "__null__"}
            )
            result = filter_instance.queryset(request, all_books)
            self.assertEqual(list(result.values_list("title", flat=True)), ["Orphan"])

        with self.subTest("regular value filters by lookup"):
            filter_instance = self._build(
                parameter_name="author",
                used_parameters={"author": str(author.pk)},
            )
            result = filter_instance.queryset(request, all_books)
            self.assertEqual(list(result.values_list("title", flat=True)), ["HP"])

        with self.subTest("multiple values filter with __in"):
            filter_instance = self._build(
                parameter_name="author",
                used_parameters={"author": f"{author.pk},{tolkien.pk}"},
                multiple=True,
            )
            result = filter_instance.queryset(request, all_books)
            self.assertEqual(
                set(result.values_list("title", flat=True)), {"HP", "LOTR"}
            )

        with self.subTest("multiple values combine __in with the null lookup"):
            filter_instance = self._build(
                parameter_name="author",
                used_parameters={"author": f"{author.pk},__null__"},
                multiple=True,
            )
            result = filter_instance.queryset(request, all_books)
            self.assertEqual(
                set(result.values_list("title", flat=True)), {"HP", "Orphan"}
            )

        with self.subTest("multiple with only the null value selected"):
            filter_instance = self._build(
                parameter_name="author",
                used_parameters={"author": "__null__"},
                multiple=True,
            )
            result = filter_instance.queryset(request, all_books)
            self.assertEqual(list(result.values_list("title", flat=True)), ["Orphan"])

    def test_media(self):
        with self.subTest("css is always the same"):
            filter_instance = self._build()
            css_html = str(filter_instance.media["css"])
            self.assertIn(
                'href="/static/admin/css/vendor/select2/select2.css"', css_html
            )
            self.assertIn(
                'href="/static/admin_select_filter/css/admin_select2_filter.css"',
                css_html,
            )

        with self.subTest("sync, searchable, single: import map + core.js only"):
            filter_instance = self._build(
                async_call=False, searchable=True, multiple=False
            )
            js_html = str(filter_instance.media["js"])
            self.assertIn('type="importmap"', js_html)
            self.assertIn('"core": "/static/admin_select_filter/js/core.js"', js_html)
            self.assertIn('type="module"', js_html)
            self.assertIn('src="/static/admin_select_filter/js/core.js"', js_html)
            self.assertLess(js_html.index("importmap"), js_html.index('type="module"'))
            self.assertNotIn("async_options.js", js_html)
            self.assertNotIn("non_searchable.js", js_html)
            self.assertNotIn("multiple_navigation.js", js_html)

        with self.subTest("async_call adds async_options.js"):
            filter_instance = self._build(async_call=True)
            self.assertIn(
                "admin_select_filter/js/async_options.js",
                str(filter_instance.media["js"]),
            )

        with self.subTest("searchable = False adds non_searchable.js"):
            filter_instance = self._build(searchable=False)
            self.assertIn(
                "admin_select_filter/js/non_searchable.js",
                str(filter_instance.media["js"]),
            )

        with self.subTest("multiple adds multiple_navigation.js"):
            filter_instance = self._build(multiple=True)
            self.assertIn(
                "admin_select_filter/js/multiple_navigation.js",
                str(filter_instance.media["js"]),
            )

        with self.subTest("every capability combined, in a fixed order"):
            filter_instance = self._build(
                async_call=True, searchable=False, multiple=True
            )
            js_html = str(filter_instance.media["js"])
            names = [
                "importmap",
                "core.js",
                "async_options.js",
                "non_searchable.js",
                "multiple_navigation.js",
            ]
            positions = [js_html.index(name) for name in names]
            self.assertEqual(positions, sorted(positions))
            self.assertEqual(js_html.count("<script"), 5)

        with self.subTest("no request attribute at all: no CSP nonce, no crash"):
            filter_instance = self._build()
            self.assertNotIn("nonce", str(filter_instance.media["js"]))

        with self.subTest("request without csp_nonce: no CSP nonce"):
            filter_instance = self._build(request=RequestFactory().get("/admin/"))
            self.assertNotIn("nonce", str(filter_instance.media["js"]))

        with self.subTest("csp_nonce picked up from the request"):
            request = RequestFactory().get("/admin/")
            setattr(request, "csp_nonce", "abc123")  # noqa: B010
            filter_instance = self._build(request=request)
            js_html = str(filter_instance.media["js"])
            self.assertEqual(js_html.count('nonce="abc123"'), 2)

    def test_choices(self):
        with self.subTest("single selection"):
            filter_instance = self._build(
                parameter_name="x",
                used_parameters={},
                lookup_choices=[("a", "Label A"), ("b", "Label B")],
            )
            choices = list(filter_instance.choices(_FakeChangeList()))
            self.assertEqual([choice["key"] for choice in choices], ["", "a", "b"])
            self.assertEqual(
                [choice["display"] for choice in choices],
                ["All", "Label A", "Label B"],
            )
            self.assertTrue(choices[0]["selected"])
            self.assertFalse(choices[1]["selected"])
            self.assertFalse(choices[2]["selected"])

        with self.subTest("multiple selection marks every selected key"):
            filter_instance = self._build(
                parameter_name="x",
                used_parameters={"x": "a,b"},
                multiple=True,
                lookup_choices=[("a", "Label A"), ("b", "Label B"), ("c", "Label C")],
            )
            choices = list(filter_instance.choices(_FakeChangeList()))
            self.assertEqual(
                [choice["selected"] for choice in choices], [False, True, True, False]
            )

    def test_option_item_hooks_are_abstract(self):
        with self.subTest("_option_items"):
            filter_instance = self._build()
            with self.assertRaises(NotImplementedError):
                filter_instance._option_items()

        with self.subTest("_selected_option_items"):
            filter_instance = self._build()
            with self.assertRaises(NotImplementedError):
                filter_instance._selected_option_items()

        with self.subTest("get_async_options delegates to _option_items"):
            filter_instance = self._build()
            with self.assertRaises(NotImplementedError):
                filter_instance.get_async_options(RequestFactory().get("/api/"), "")

        with self.subTest("lookups delegates to _option_items when not async"):
            filter_instance = self._build(async_call=False)
            with self.assertRaises(NotImplementedError):
                filter_instance.lookups(RequestFactory().get("/admin/"), None)

        with self.subTest("lookups delegates to _selected_option_items when async"):
            filter_instance = self._build(async_call=True)
            with self.assertRaises(NotImplementedError):
                filter_instance.lookups(RequestFactory().get("/admin/"), None)

    def test_get_async_options_delegates_to_option_items(self):
        filter_instance = self._build(
            nullable=False,
            parameter_name="x",
            _option_items=lambda request=None, q="": [("1", "One")],
        )
        options = filter_instance.get_async_options(RequestFactory().get("/api/"), "")
        self.assertEqual(options, [(filter_instance.all_value, "All"), ("1", "One")])

    def test_lookups_dispatches_by_async_call_and_appends_null_option(self):
        with self.subTest("sync mode uses _option_items"):
            filter_instance = self._build(
                async_call=False,
                has_null_option=False,
                _option_items=lambda request=None, q="": [("1", "One")],
                _selected_option_items=lambda: [],
            )
            result = filter_instance.lookups(RequestFactory().get("/admin/"), None)
            self.assertEqual(result, [("1", "One")])

        with self.subTest("async mode uses _selected_option_items"):
            filter_instance = self._build(
                async_call=True,
                has_null_option=False,
                _option_items=lambda request=None, q="": [],
                _selected_option_items=lambda: [("2", "Two")],
            )
            result = filter_instance.lookups(RequestFactory().get("/admin/"), None)
            self.assertEqual(result, [("2", "Two")])

        with self.subTest("null option appended when present"):
            filter_instance = self._build(
                async_call=False,
                has_null_option=True,
                _option_items=lambda request=None, q="": [("1", "One")],
            )
            result = filter_instance.lookups(RequestFactory().get("/admin/"), None)
            self.assertEqual(result, [("1", "One"), (filter_instance.null_value, "-")])


class ForeignKeyFilterTests(TestCase):
    def _build_filter(self, request, params=None):
        model_admin = admin.site._registry[Book]
        return AuthorFilter(request, params or {}, Book, model_admin)

    def test__resolve_model(self):
        with self.subTest("no parameter_name"):
            filter_instance = ForeignKeyFilter.__new__(ForeignKeyFilter)
            filter_instance.parameter_name = None
            assert filter_instance._resolve_model(Book) is None

        with self.subTest("unknown field"):
            filter_instance = ForeignKeyFilter.__new__(ForeignKeyFilter)
            filter_instance.parameter_name = "does_not_exist"
            assert filter_instance._resolve_model(Book) is None

        with self.subTest("plain relation field"):
            filter_instance = ForeignKeyFilter.__new__(ForeignKeyFilter)
            filter_instance.parameter_name = "author"
            assert filter_instance._resolve_model(Book) is Author

        with self.subTest("nested relation chain"):
            filter_instance = ForeignKeyFilter.__new__(ForeignKeyFilter)
            filter_instance.parameter_name = "author__country"
            assert filter_instance._resolve_model(Book) is Country

        with self.subTest("final segment isn't a relation"):
            filter_instance = ForeignKeyFilter.__new__(ForeignKeyFilter)
            filter_instance.parameter_name = "title"
            assert filter_instance._resolve_model(Book) is None

    def test_get_options(self):
        # Each subTest wraps its writes in a rolled-back savepoint so that
        # authors/books created by one scenario don't leak into the next,
        # since subTests share the surrounding test method's transaction.
        with self.subTest("only used values by default"), transaction.atomic():
            used = Author.objects.create(name="Used")
            Author.objects.create(name="Unused")
            Book.objects.create(title="A Book", author=used)
            request = RequestFactory().get("/admin/tests/book/")
            filter_instance = self._build_filter(request)
            assert list(filter_instance.get_options()) == [used]
            transaction.set_rollback(True)

        with (
            self.subTest("all values when filter_only_used_values is False"),
            transaction.atomic(),
        ):
            unused = Author.objects.create(name="Unused")
            request = RequestFactory().get("/admin/")
            filter_instance = AllNullableAuthorFilter(
                request, {}, Book, admin.site._registry[Book]
            )
            assert list(filter_instance.get_options()) == [unused]
            transaction.set_rollback(True)

        with self.subTest("respects only fields"), transaction.atomic():
            author = Author.objects.create(name="Solo")
            Book.objects.create(title="Book", author=author)
            request = RequestFactory().get("/admin/")
            filter_instance = OnlyNameAuthorFilter(
                request, {}, Book, admin.site._registry[Book]
            )
            assert list(filter_instance.get_options()) == [author]
            transaction.set_rollback(True)

        with self.subTest("searches related admin"), transaction.atomic():
            match = Author.objects.create(name="Rowling")
            Author.objects.create(name="Tolkien")
            Book.objects.create(title="HP", author=match)
            Book.objects.create(title="LOTR", author=Author.objects.get(name="Tolkien"))
            request = RequestFactory().get("/admin/")
            filter_instance = self._build_filter(request)
            assert list(filter_instance.get_options(q="Rowl")) == [match]
            transaction.set_rollback(True)

        with (
            self.subTest("deduplicates when related admin reports duplicates"),
            transaction.atomic(),
        ):
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
            transaction.set_rollback(True)

    def test__option_items(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get("/admin/")
        filter_instance = self._build_filter(request)
        assert filter_instance._option_items(
            request=RequestFactory().get("/api/"), q=""
        ) == [(str(author.pk), "Rowling")]

    def test__selected_option_items(self):
        with self.subTest("no selection returns empty"):
            request = RequestFactory().get("/admin/tests/book/")
            filter_instance: BaseSelectFilter = AsyncAuthorFilter(
                request, {}, Book, admin.site._registry[Book]
            )
            assert filter_instance._selected_option_items() == []

        with self.subTest("single selection returns the matching instance"):
            author = Author.objects.create(name="Tolkien")
            request = RequestFactory().get(
                "/admin/tests/book/", {"author": str(author.pk)}
            )
            filter_instance = AsyncAuthorFilter(
                request,
                {"author": [str(author.pk)]},
                Book,
                admin.site._registry[Book],
            )
            assert filter_instance._selected_option_items() == [
                (str(author.pk), "Tolkien")
            ]

        with self.subTest("multiple selection returns every selected instance"):
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


class ChoiceFilterTests(TestCase):
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

    def test_template_renders_searchable_data_attribute(self):
        request = RequestFactory().get("/admin/")

        with self.subTest("searchable by default: attribute omitted"):
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

        with self.subTest("searchable disabled"):
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

    def test_get_options(self):
        with self.subTest("only used values by default"):
            Book.objects.create(title="Dune", genre="fiction")
            request = RequestFactory().get("/admin/")
            filter_instance = self._build_filter(GenreFilter, request)
            assert filter_instance.get_options() == [("fiction", "Fiction")]

        with self.subTest("all values when filter_only_used_values is False"):
            request = RequestFactory().get("/admin/")
            filter_instance = self._build_filter(AllGenresFilter, request)
            assert filter_instance.get_options() == [
                ("fiction", "Fiction"),
                ("nonfiction", "Non-fiction"),
                ("poetry", "Poetry"),
            ]

        with self.subTest("searches by label substring"):
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

    def test__selected_option_items(self):
        with self.subTest("no selection returns empty"):
            request = RequestFactory().get("/admin/tests/book/")
            filter_instance = self._build_filter(AsyncGenreFilter, request)
            assert filter_instance._selected_option_items() == []

        with self.subTest("single selection returns the matching option"):
            request = RequestFactory().get("/admin/tests/book/", {"genre": "fiction"})
            filter_instance = self._build_filter(
                AsyncGenreFilter, request, {"genre": ["fiction"]}
            )
            assert filter_instance._selected_option_items() == [("fiction", "Fiction")]

        with self.subTest("multiple selection returns every selected option"):
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


class FieldListFilterTests(TestCase):
    """Tests for the ``list_filter = [("field", field_list_filter(...))]`` form."""

    def _resolved_field(self, model, field_path):
        for part in field_path.split("__")[:-1]:
            model = model._meta.get_field(part).related_model
        return model._meta.get_field(field_path.rsplit("__", 1)[-1])

    def test_produces_a_correctly_bound_instance(self):
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

        with self.subTest("infers parameter_name from field_path"):
            self.assertEqual(filter_instance.parameter_name, "author__country")

        with self.subTest("infers the target model from the nested lookup"):
            self.assertIs(filter_instance.model, Country)

        with self.subTest("behaves like a normal ForeignKeyFilter"):
            self.assertEqual(list(filter_instance.get_options()), [country])

    def test_falls_back_to_field_name_without_field_path(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = Book._meta.get_field("genre")

        factory = field_list_filter(ChoiceFilter)
        filter_instance = factory(field, request, {}, Book, model_admin)

        self.assertEqual(filter_instance.parameter_name, "genre")

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

        self.assertIs(type(first), type(second))

    def test_rejects_an_async_call_filter(self):
        class AsyncFK(ForeignKeyFilter):
            async_call = True

        with self.assertRaisesRegex(TypeError, "doesn't support async_call"):
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

        self.assertEqual(len(matching), 1)
        self.assertEqual(list(matching[0].get_options()), [country])
