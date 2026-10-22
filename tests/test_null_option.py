"""NullOptionMixin: the empty-value option, and its label."""

from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.utils.translation import gettext_lazy
from unittest_parametrize import parametrize

from django_admin_select_filter.filters import BaseSelectFilter, ForeignKeyFilter
from tests.cases import SelectFilterCase, _FakeModelAdmin
from tests.test_admin_autocomplete import AuthorAutocompleteFilter, build
from tests.testapp.models import Author, Book


class TestNullOptionMixin(SelectFilterCase):
    """NullOptionMixin: the empty-value option, and its label."""

    @parametrize(
        ("parameter_name", "expected"),
        [
            ("author", True),
            ("title", False),
            ("author_id", True),
            ("does_not_exist", False),
        ],
        ids=[
            "nullable_field_matched_by_name",
            "non_nullable_field_matched_by_name",
            "nullable_field_matched_by_attname",
            "field_that_doesn_t_exist",
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


class AuthorFilter(ForeignKeyFilter):
    parameter_name = "author"
    filter_only_used_values = False


def null_option(filter_class, site=admin.site, request=None):
    request = request or RequestFactory().get("/admin/testapp/book/")
    request.user = AnonymousUser()
    filter_instance = filter_class(request, {}, Book, site._registry[Book])
    options = filter_instance.lookups(request, site._registry[Book])
    return dict(options).get(filter_instance.null_value)


class TestNullLabel(TestCase):
    """The empty-value option's text."""

    def test_default_is_the_admin_empty_value_display(self):
        Author.objects.create(name="Rowling")
        assert null_option(AuthorFilter) == "-"

        with patch.object(
            type(admin.site._registry[Book]),
            "empty_value_display",
            "(none)",
            create=True,
        ):
            assert null_option(AuthorFilter) == "(none)"

    def test_null_label_and_get_null_label(self):
        class Labelled(AuthorFilter):
            null_label = gettext_lazy("No author")

        class PerRequest(AuthorFilter):
            def get_null_label(self, request):
                return "Anonymous" if request.GET.get("anon") else "Nobody"

        assert null_option(Labelled) == "No author"
        assert null_option(PerRequest) == "Nobody"
        request = RequestFactory().get("/admin/testapp/book/", {"anon": "1"})
        assert null_option(PerRequest, request=request) == "Anonymous"

    def test_without_a_model_admin_it_is_a_dash(self):
        filter_instance = BaseSelectFilter.__new__(BaseSelectFilter)

        assert filter_instance.get_null_label(None) == "-"
        assert filter_instance.null_label_display == "-"

    def test_async_options_and_the_admin_autocomplete_use_it(self):
        class Labelled(AuthorAutocompleteFilter):
            null_label = "No author"

        filter_instance = build(Labelled)
        html = render_to_string(
            filter_instance.template,
            {"spec": filter_instance, "title": filter_instance.title, "choices": []},
        )
        assert 'data-null-label="No author"' in html

        class AsyncLabelled(AuthorFilter):
            async_call = True
            null_label = "No author"

        request = RequestFactory().get("/admin/testapp/book/")
        request.user = AnonymousUser()
        async_filter = AsyncLabelled(request, {}, Book, admin.site._registry[Book])
        options = async_filter._build_async_options(request, [("1", "One")])
        assert options[-1] == ("__null__", "No author")
