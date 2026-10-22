"""The features of BaseSelectFilter, one mixin each."""

from django.forms import Media
from django.test import RequestFactory, SimpleTestCase

from django_admin_select_filter import mixins
from django_admin_select_filter.filters import BaseSelectFilter


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
        assert str(mixins.SelectFilterFeature.media.fget(build())) == str(Media())

    def test_several_values_none_selected(self):
        assert build(multiple=True).selected_values() == []
        assert build(multiple=False).selected_values() == []

    def test_the_async_options_of_several_values_have_no_all(self):
        assert build(multiple=True).leading_async_options() == []
        assert build(multiple=False).leading_async_options() == [("__all__", "All")]

    def test_the_names_still_importable_from_filters(self):
        from django_admin_select_filter.filters import ASYNC_CALL_URL_NAME

        assert ASYNC_CALL_URL_NAME == mixins.ASYNC_CALL_URL_NAME == "options"
