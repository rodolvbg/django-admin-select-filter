"""BaseSelectFilter: what every filter shares, and its features put together."""

import pytest
from django.forms import Media
from django.test import RequestFactory, SimpleTestCase
from unittest_parametrize import parametrize

from django_admin_select_filter import mixins
from django_admin_select_filter.filters import (
    BaseSelectFilter,
)
from tests.cases import (
    SelectFilterCase,
    _FakeChangeList,
    _FakeModelAdmin,
)
from tests.testapp.models import Author, Book


class TestBaseSelectFilter(SelectFilterCase):
    """The shared base: configuration, Select2, queryset, choices and media."""

    def test_model_admin_queryset_caches_the_admin_queryset(self):
        model_admin = _FakeModelAdmin(Book.objects.all())
        filter_instance = self._build(
            model_admin=model_admin, request=RequestFactory().get("/admin/")
        )

        first = filter_instance.model_admin_queryset
        second = filter_instance.model_admin_queryset

        assert first is second
        assert model_admin.calls == 1

    @parametrize(
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
            "no_parameter_name",
            "single_segment_valid_field",
            "single_segment_unknown_field",
            "nested_valid_relation_chain",
            "nested_unknown_middle_segment",
            "nested_non_relation_middle_segment",
            "nested_unknown_final_segment",
        ],
    )
    def test__resolve_field(self, parameter_name, expected_name):
        filter_instance = self._build()
        filter_instance.parameter_name = parameter_name

        field = filter_instance._resolve_field(Book)

        assert (field.name if field is not None else None) == expected_name

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

    def test_option_items_is_abstract(self):
        filter_instance = self._build()
        with pytest.raises(NotImplementedError):
            filter_instance._option_items()

    def test_selected_option_items_is_abstract(self):
        filter_instance = self._build()
        with pytest.raises(NotImplementedError):
            filter_instance._selected_option_items()

    def test_lookups_requires_option_items_when_not_async(
        self,
    ):
        filter_instance = self._build(async_call=False)
        with pytest.raises(NotImplementedError):
            filter_instance.lookups(RequestFactory().get("/admin/"), None)

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


def build(**attrs):
    """A BaseSelectFilter with only the attributes the test needs."""
    instance = BaseSelectFilter.__new__(BaseSelectFilter)
    instance.request = RequestFactory().get("/admin/")
    instance.used_parameters = {}
    instance.parameter_name = "author"
    for name, value in attrs.items():
        setattr(instance, name, value)
    return instance


def scripts(media):
    return [str(script) for script in media._js]


class TestFeatures(SimpleTestCase):
    def test_base_select_filter_is_every_feature(self):
        for feature in (
            mixins.UsedValuesMixin,
            mixins.NullOptionMixin,
            mixins.MultipleValuesMixin,
            mixins.SearchableMixin,
            mixins.AsyncOptionsMixin,
        ):
            assert issubclass(BaseSelectFilter, feature), feature

    def test_each_adds_its_script_only_when_on(self):
        off = build(multiple=False, searchable=True, async_call=False)
        assert [s for s in scripts(off.media) if "core.js" not in s] == []

        on = build(multiple=True, searchable=False, async_call=True)
        names = [s.split("/js/")[1].split('"')[0] for s in scripts(on.media)]
        # Select2's first, then each feature's, in the order they always were.
        assert names == [
            "core.js",
            "async_options.js",
            "non_searchable.js",
            "multiple_navigation.js",
        ]

    def test_a_feature_alone_adds_nothing_of_its_own(self):
        media = mixins.SelectFilterFeature.media.fget(build())  # type: ignore[attr-defined]
        assert str(media) == str(Media())

    def test_several_values_none_selected(self):
        assert build(multiple=True).selected_values() == []
        assert build(multiple=False).selected_values() == []

    def test_the_async_options_of_several_values_have_no_all(self):
        assert build(multiple=True).leading_async_options() == []
        assert build(multiple=False).leading_async_options() == [("__all__", "All")]

    def test_the_names_still_importable_from_filters(self):
        from django_admin_select_filter.filters import ASYNC_CALL_URL_NAME

        assert ASYNC_CALL_URL_NAME == mixins.ASYNC_CALL_URL_NAME == "options"


class TestChoicesTypeAlias(SimpleTestCase):
    """The ``Choices`` alias of ``django_admin_select_filter.types``."""

    def test_choices_type_alias_is_importable(self):
        # Only imported under TYPE_CHECKING by the package itself.
        from django_admin_select_filter.types import Choices

        assert Choices == list[tuple[str, str]]
