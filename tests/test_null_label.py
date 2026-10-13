"""``null_label`` / ``get_null_label()``: the empty-value option's text."""

import pytest
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils.translation import gettext_lazy

from django_admin_select_filter.filters import BaseSelectFilter, ForeignKeyFilter
from tests.test_admin_autocomplete import AuthorAutocompleteFilter, build
from tests.testapp.models import Author, Book


class AuthorFilter(ForeignKeyFilter):
    parameter_name = "author"
    filter_only_used_values = False


def null_option(filter_class, site=admin.site, request=None):
    request = request or RequestFactory().get("/admin/testapp/book/")
    request.user = AnonymousUser()
    filter_instance = filter_class(request, {}, Book, site._registry[Book])
    options = filter_instance.lookups(request, site._registry[Book])
    return dict(options).get(filter_instance.null_value)


@pytest.mark.django_db
def test_default_is_the_admin_empty_value_display(monkeypatch):
    Author.objects.create(name="Rowling")
    assert null_option(AuthorFilter) == "-"

    monkeypatch.setattr(
        type(admin.site._registry[Book]), "empty_value_display", "(none)", raising=False
    )
    assert null_option(AuthorFilter) == "(none)"


@pytest.mark.django_db
def test_null_label_and_get_null_label():
    class Labelled(AuthorFilter):
        null_label = gettext_lazy("No author")

    class PerRequest(AuthorFilter):
        def get_null_label(self, request):
            return "Anonymous" if request.GET.get("anon") else "Nobody"

    assert null_option(Labelled) == "No author"
    assert null_option(PerRequest) == "Nobody"
    request = RequestFactory().get("/admin/testapp/book/", {"anon": "1"})
    assert null_option(PerRequest, request=request) == "Anonymous"


def test_without_a_model_admin_it_is_a_dash():
    filter_instance = BaseSelectFilter.__new__(BaseSelectFilter)

    assert filter_instance.get_null_label(None) == "-"
    assert filter_instance.null_label_display == "-"


@pytest.mark.django_db
def test_async_options_and_the_admin_autocomplete_use_it():
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
