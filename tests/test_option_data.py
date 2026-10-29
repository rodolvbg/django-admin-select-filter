"""get_option_data() and option_template: more of each option, for the page."""

import html
import json
import re
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from tests.cases import _adapt_filter_params_to_django_version, _FakeChangeList
from tests.testapp.admin import (
    AsyncAuthorFilter,
    AsyncGenreFilter,
    AuthorFilter,
    GenreFilter,
)
from tests.testapp.models import Author, Book


def note(self, value, label, obj=None):
    """Something of each: its kind of option, and the object's name."""
    return {"note": obj.name if obj is not None else f"choice {value}"}


class TestOptionData(TestCase):
    user: User
    rowling: Author

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("admin", "a@example.com", "pw")
        cls.rowling = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=cls.rowling, genre="fiction")

    def setUp(self):
        patcher = _adapt_filter_params_to_django_version()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.user)

    def render(self, filter_class, params=None):
        request = RequestFactory().get("/admin/testapp/book/")
        spec = filter_class(request, params or {}, Book, admin.site._registry[Book])
        return render_to_string(
            spec.template,
            {
                "spec": spec,
                "title": spec.title,
                "choices": list(spec.choices(_FakeChangeList())),
            },
            request=request,
        )

    def options(self, page):
        return {
            # As the browser reads the attribute.
            match.group(1): json.loads(html.unescape(match.group(2)))
            for match in re.finditer(
                r'data-key="([^"]*)"\s+data-option="([^"]*)"', page
            )
        }

    def test_nothing_by_default(self):
        html = self.render(AuthorFilter)
        assert "data-option=" not in html
        assert "data-option-template" not in html

    def test_its_data_on_each_option_of_a_foreign_key(self):
        with patch.object(AuthorFilter, "get_option_data", note):
            html = self.render(AuthorFilter)
        assert self.options(html) == {
            str(self.rowling.pk): {"data": {"note": "Rowling"}}
        }

    def test_and_of_choices(self):
        with patch.object(GenreFilter, "get_option_data", note):
            html = self.render(GenreFilter)
        assert self.options(html) == {"fiction": {"data": {"note": "choice fiction"}}}

    def test_its_template_rendered_for_each(self):
        with (
            patch.object(AuthorFilter, "get_option_data", note),
            patch.object(AuthorFilter, "option_template", "testapp/option.html"),
        ):
            html = self.render(AuthorFilter)
        assert 'data-option-template="true"' in html
        [option] = self.options(html).values()
        assert option["html"].strip() == (
            f"<b>Rowling</b> · {self.rowling.pk} <i>Rowling</i>"
        )
        # Its label escaped, as any template's.
        Author.objects.filter(pk=self.rowling.pk).update(name="<Rowling>")
        with patch.object(AuthorFilter, "option_template", "testapp/option.html"):
            html = self.render(AuthorFilter)
        [option] = self.options(html).values()
        assert option == {"html": f"<b>&lt;Rowling&gt;</b> · {self.rowling.pk}\n"}

    def test_in_the_api_results(self):
        url = reverse("admin_select_filter:options")
        query = {
            "app_label": "testapp",
            "model_name": "book",
            "parameter_name": "author",
        }
        with (
            patch.object(AsyncAuthorFilter, "get_option_data", note),
            patch.object(AsyncAuthorFilter, "option_template", "testapp/option.html"),
        ):
            results = self.client.get(url, query).json()["results"]
        assert results[0] == {"id": "__all__", "text": "All"}  # As it is.
        rowling = next(r for r in results if r["id"] == str(self.rowling.pk))
        assert rowling["data"] == {"note": "Rowling"}
        assert rowling["html"].startswith("<b>Rowling</b>")
        with patch.object(AsyncGenreFilter, "get_option_data", note):
            results = self.client.get(url, {**query, "parameter_name": "genre"}).json()[
                "results"
            ]
        assert {
            "id": "fiction",
            "text": "Fiction",
            "data": {"note": "choice fiction"},
        } in results

    def test_the_selected_ones_of_an_async_filter(self):
        with patch.object(AsyncAuthorFilter, "get_option_data", note):
            html = self.render(AsyncAuthorFilter, {"author": [str(self.rowling.pk)]})
        assert self.options(html) == {
            str(self.rowling.pk): {"data": {"note": "Rowling"}}
        }
        with patch.object(AsyncGenreFilter, "get_option_data", note):
            html = self.render(AsyncGenreFilter, {"genre": ["fiction"]})
        assert self.options(html) == {"fiction": {"data": {"note": "choice fiction"}}}

    def test_an_option_without_any(self):
        request = RequestFactory().get("/")
        spec = AuthorFilter(request, {}, Book, admin.site._registry[Book])
        assert spec.option_extra("999") == {}
