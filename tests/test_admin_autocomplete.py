"""``ForeignKeyFilter.admin_autocomplete``: options from ``admin:autocomplete``."""

import pytest
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from django_admin_select_filter.filters import ChoiceFilter, ForeignKeyFilter
from tests.testapp.models import Author, Book


class AuthorAutocompleteFilter(ForeignKeyFilter):
    parameter_name = "author"
    admin_autocomplete = True


class CountryAutocompleteFilter(ForeignKeyFilter):
    parameter_name = "author__country"
    admin_autocomplete = True


class _FakeChangeList:
    add_facets = False

    def get_query_string(self, new_params=None, remove=None):
        return "?"


def build(filter_class, site=admin.site, params=None, user=None):
    request = RequestFactory().get("/admin/testapp/book/", params or {})
    request.user = user
    model_admin = site._registry[Book]
    return filter_class(request, dict(params or {}), Book, model_admin)


@pytest.fixture
def country_site(monkeypatch):
    # A routed site, whose Country admin gets search_fields for the test.
    from tests.testapp.admin import E2ECountryAdmin, e2e_admin_site

    monkeypatch.setattr(E2ECountryAdmin, "search_fields", ["name"])
    return e2e_admin_site


@pytest.mark.django_db
def test_uses_the_admin_autocomplete_endpoint():
    filter_instance = build(AuthorAutocompleteFilter)

    assert filter_instance.async_call is True
    assert filter_instance.async_call_url == reverse("admin:autocomplete")
    assert filter_instance.autocomplete_source == {
        "app_label": "testapp",
        "model_name": "book",
        "field_name": "author",
    }
    assert "admin_select_filter/js/async_options.js" in str(filter_instance.media["js"])


@pytest.mark.django_db
def test_nested_lookups_ask_about_the_last_relation(country_site):
    filter_instance = build(CountryAutocompleteFilter, site=country_site)

    assert filter_instance.async_call_url == reverse("e2e_admin:autocomplete")
    assert filter_instance.autocomplete_source == {
        "app_label": "testapp",
        "model_name": "author",
        "field_name": "country",
    }


@pytest.mark.django_db
def test_template_tells_the_js_where_to_ask():
    author = Author.objects.create(name="Rowling")
    filter_instance = build(AuthorAutocompleteFilter, params={"author": str(author.pk)})
    html = render_to_string(
        filter_instance.template,
        {
            "spec": filter_instance,
            "title": filter_instance.title,
            "choices": list(filter_instance.choices(_FakeChangeList())),
        },
    )

    assert f'data-api-url="{reverse("admin:autocomplete")}"' in html
    assert 'data-admin-autocomplete="true"' in html
    assert 'data-source-app-label="testapp"' in html
    assert 'data-source-model-name="book"' in html
    assert 'data-source-field-name="author"' in html
    assert 'data-all-label="All"' in html
    assert 'data-null-value="__null__"' in html  # Book.author is nullable
    assert "Rowling" in html  # the selected option is rendered


@pytest.mark.django_db
def test_misconfigurations_are_explained():
    class GenreAutocompleteFilter(ForeignKeyFilter):
        parameter_name = "genre"
        model = Author  # not a relation, whatever the model
        admin_autocomplete = True

    with pytest.raises(ImproperlyConfigured, match="ForeignKey or a ManyToManyField"):
        build(GenreAutocompleteFilter)

    # Country has no ModelAdmin with search_fields on the default site.
    with pytest.raises(ImproperlyConfigured, match="search_fields for Country"):
        build(CountryAutocompleteFilter)

    assert not hasattr(ChoiceFilter, "admin_autocomplete")


@pytest.mark.django_db
@pytest.mark.filterwarnings("ignore::django.core.paginator.UnorderedObjectListWarning")
def test_the_endpoint_answers_for_the_filter(admin_client):
    Author.objects.create(name="Rowling")
    Author.objects.create(name="Tolkien")
    response = admin_client.get(
        reverse("admin:autocomplete"),
        {
            "term": "row",
            "app_label": "testapp",
            "model_name": "book",
            "field_name": "author",
        },
    )

    assert response.status_code == 200
    assert [item["text"] for item in response.json()["results"]] == ["Rowling"]


@pytest.mark.django_db
def test_selected_values_filter_the_changelist():
    rowling = Author.objects.create(name="Rowling")
    Book.objects.create(title="HP", author=rowling)
    Book.objects.create(title="Other")
    filter_instance = build(
        AuthorAutocompleteFilter, params={"author": str(rowling.pk)}
    )

    result = filter_instance.queryset(filter_instance.request, Book.objects.all())
    assert list(result.values_list("title", flat=True)) == ["HP"]
