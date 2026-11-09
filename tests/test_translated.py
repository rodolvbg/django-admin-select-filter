"""Translated parameters and values: ``?genero=ficcion`` in Spanish,
``?genre=fiction`` in English, either understood in both."""

import re

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.translation import override, pgettext_lazy

from django_admin_select_filter.mixins import translations
from django_admin_select_filter.views import Select2FilterOptionsView
from tests.cases import _adapt_filter_params_to_django_version
from tests.testapp.admin import (
    AsyncTranslatedGenreFilter,
    GenreFilter,
    I18nBookAdmin,
    MultipleTranslatedGenreFilter,
    TranslatedAuthorFilter,
    TranslatedGenreFilter,
    UnboundTranslatedFilter,
    i18n_admin_site,
)
from tests.testapp.models import Author, Book

BOOKS = "/i18n-admin/testapp/book/"


def titles(html):
    """The books of a changelist's page."""
    return sorted(re.findall(r'class="field-__str__"><a [^>]*>([^<]+)</a>', html))


def options(html):
    """Its options' values, and which are selected."""
    return [
        (key, " selected" if re.search(r"\sselected\s", rest) else "")
        for key, rest in re.findall(r'<option\s+data-key="([^"]*)"(.*?)>', html, re.S)
    ]


class TestTranslated(TestCase):
    user: User
    author: Author

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("admin", "a@example.com", "pw")
        cls.author = Author.objects.create(name="Borges")
        Book.objects.create(title="Ficciones", genre="fiction", author=cls.author)
        Book.objects.create(title="Fervor", genre="poetry")
        Book.objects.create(title="Essays", genre="nonfiction")

    def setUp(self):
        self.client.force_login(self.user)

    def page(self, language, query):
        with override(language):
            return self.client.get(BOOKS, query).content.decode()

    def test_in_the_active_language(self):
        html = self.page("es", {"genero": "ficcion"})
        assert titles(html) == ["Ficciones"]
        assert ("ficcion", " selected") in options(html)
        # Not translated: its own.
        assert ("nonfiction", "") in options(html)
        html = self.page("en", {"genre": "fiction"})
        assert titles(html) == ["Ficciones"]
        assert ("fiction", " selected") in options(html)

    def test_another_languages_link(self):
        """A language switched keeps its query: understood, as this one's."""
        html = self.page("en", {"genero": "poesia"})
        assert titles(html) == ["Fervor"]
        assert ("poetry", " selected") in options(html)

    def test_its_own_values(self):
        """Links before its values were translated."""
        assert titles(self.page("es", {"genero": "poetry"})) == ["Fervor"]
        assert titles(self.page("es", {"genero": "nonfiction"})) == ["Essays"]

    def test_a_foreign_keys_translated_parameter(self):
        html = self.page("es", {"autor": self.author.pk})
        assert titles(html) == ["Ficciones"]
        assert titles(self.page("en", {"autor": self.author.pk})) == ["Ficciones"]


class TestFilter(TestCase):
    def setUp(self):
        patcher = _adapt_filter_params_to_django_version()
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, filter_class, params):
        request = RequestFactory().get("/")
        return filter_class(
            request, params, Book, i18n_admin_site._registry[Book]
        )

    def test_several_values(self):
        Book.objects.create(title="Ficciones", genre="fiction")
        Book.objects.create(title="Fervor", genre="poetry")
        Book.objects.create(title="Empty")
        with override("es"):
            spec = self.build(
                MultipleTranslatedGenreFilter, {"genre": ["fiction,poesia,__null__"]}
            )
            assert spec.selected_values() == ["ficcion", "poesia", "__null__"]
            books = spec.queryset(None, Book.objects.all())
        assert sorted(book.title for book in books) == ["Empty", "Fervor", "Ficciones"]

    def test_without_its_lookup(self):
        with pytest.raises(ImproperlyConfigured, match="field_name"):
            self.build(UnboundTranslatedFilter, {})

    def test_facet_counts_by_their_values_in_the_url(self):
        Book.objects.create(title="Ficciones", genre="fiction")
        Book.objects.create(title="Empty")
        with override("es"):
            spec = self.build(TranslatedGenreFilter, {})
            assert spec._get_option_facet_counts() == {"ficcion": 1, "__null__": 1}


class TestLinks:
    def test_query(self):
        with override("es"):
            assert TranslatedGenreFilter.query("fiction") == {"genero": "ficcion"}
            assert MultipleTranslatedGenreFilter.query("poetry", None) == {
                "genero": "poesia,__null__"
            }
        assert TranslatedGenreFilter.query("nonfiction") == {"genre": "nonfiction"}
        # Not translated: as it is.
        assert GenreFilter.query("fiction", None) == {"genre": "fiction,__null__"}
        # A foreign key's: its ids.
        with override("es"):
            assert TranslatedAuthorFilter.query(3) == {"autor": "3"}
            assert TranslatedAuthorFilter.query(None) == {"autor": "__null__"}
        request = RequestFactory().get("/?autor=3")
        assert TranslatedAuthorFilter.selected(request) == ["3"]

    @pytest.mark.parametrize(
        "filter_class, query, expected",
        [
            (TranslatedGenreFilter, "?genero=ficcion", ["fiction"]),
            (TranslatedGenreFilter, "?genre=poesia", ["poetry"]),
            (TranslatedGenreFilter, "?genre=nonfiction", ["nonfiction"]),
            (TranslatedGenreFilter, "?other=1", []),
            (MultipleTranslatedGenreFilter, "?genero=ficcion,,__null__", [
                "fiction",
                "__null__",
            ]),
            (GenreFilter, "?genre=poetry", ["poetry"]),
        ],
    )
    def test_selected(self, filter_class, query, expected):
        request = RequestFactory().get(f"/{query}")
        assert filter_class.selected(request) == expected

    def test_translations(self):
        assert translations("genre") == {"genre": None}
        name = pgettext_lazy("filter", "genre")
        with override("es"):
            assert translations(name) == {"genero": None, "genre": "en"}


@pytest.mark.django_db
class TestAsyncOptions:
    url = reverse("admin_select_filter:options")

    @pytest.fixture(autouse=True)
    def books(self, client):
        client.force_login(User.objects.create_superuser("a", "a@example.com", "pw"))
        author = Author.objects.create(name="Borges")
        Book.objects.create(title="Ficciones", genre="fiction", author=author)

    @pytest.fixture(params=[False, True], ids=["scan", "registry"])
    def use_registry(self, request, monkeypatch):
        monkeypatch.setattr(Select2FilterOptionsView, "use_registry", request.param)
        Select2FilterOptionsView._build_async_filter_registry.cache_clear()
        yield
        Select2FilterOptionsView._build_async_filter_registry.cache_clear()

    def results(self, client, parameter_name, **query):
        response = client.get(
            self.url,
            {
                "app_label": "testapp",
                "model_name": "author",
                "parameter_name": parameter_name,
                **query,
            },
        )
        assert response.status_code == 200
        return [(r["id"], r["text"]) for r in response.json()["results"]]

    def test_in_its_pages_language(self, client, use_registry):
        """This endpoint in English (outside i18n_patterns), its page in
        Spanish: its values in Spanish."""
        assert ("ficcion", "Fiction (1)") in self.results(
            client, "genero", facets="true"
        )
        assert ("fiction", "Fiction") in self.results(client, "genre")

    def test_not_its_parameter(self, client, use_registry):
        response = client.get(
            self.url,
            {"app_label": "testapp", "model_name": "author", "parameter_name": "x"},
        )
        assert response.status_code == 404


def test_its_admin():
    assert I18nBookAdmin.list_filter[0] is TranslatedGenreFilter
    assert AsyncTranslatedGenreFilter.field_name == "books__genre"
