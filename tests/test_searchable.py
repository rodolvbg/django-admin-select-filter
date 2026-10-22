"""SearchableMixin: Select2's search input."""

from tests.cases import SelectFilterCase


class TestSearchableMixin(SelectFilterCase):
    """SearchableMixin: Select2's search input."""

    def test_media_searchable_false_adds_non_searchable_js(self):
        filter_instance = self._build(searchable=False)
        assert "admin_select_filter/js/non_searchable.js" in str(
            filter_instance.media["js"]
        )
