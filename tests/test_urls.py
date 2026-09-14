import importlib

from django.test import override_settings
from django.urls import clear_url_caches, reverse

import tests.urls as root_urls
from django_admin_select_filter import urls as select_filter_urls


def _reload_urlconf():
    # `tests.urls` captured django_admin_select_filter.urls's *urlpatterns*
    # list via include() when it was first imported, so reloading only the
    # child leaves the root urlconf pointing at the stale list. Reload both,
    # child first, then clear Django's resolver cache so it rebuilds from
    # the freshly reloaded root.
    importlib.reload(select_filter_urls)
    importlib.reload(root_urls)
    clear_url_caches()


class Select2FilterUrlsTests:
    def test_default_options_url(self):
        assert (
            reverse("admin_select_filter:options")
            == "/admin/select-filter/django_admin_select_filter/options/"
        )

    def test_options_url_path_is_configurable(self):
        try:
            with override_settings(
                DJANGO_ADMIN_SELECT_FILTERS_ASYNC_CALL_URL="custom-options/"
            ):
                _reload_urlconf()
                assert (
                    reverse("admin_select_filter:options")
                    == "/admin/select-filter/custom-options/"
                )
        finally:
            _reload_urlconf()
