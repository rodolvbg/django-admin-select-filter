import pytest
from django.contrib import admin
from django.template.loader import render_to_string
from django.test import RequestFactory

from tests.testapp.admin import AuthorFilter, BookAdmin
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
    filter_instance = _build_filter(request, {"author": str(rowling.pk)})

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

    assert 'class="admin-select2-filter"' in html
    assert 'data-parameter-name="author"' in html
    assert "Rowling" in html
