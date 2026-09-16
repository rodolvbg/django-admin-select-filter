import sys
import types

from django.urls import reverse

from django_admin_select_filter.urls import django_admin_select_filter_path


class Select2FilterUrlsTests:
    def test_default_options_url(self):
        assert (
            reverse("admin_select_filter:options")
            == "/django_admin_select_filter/options/"
        )

    def test_route_is_configurable(self):
        urlconf = types.ModuleType("tests_temp_urlconf")
        urlconf.urlpatterns = [  # type: ignore[attr-defined]
            django_admin_select_filter_path(route="custom/")
        ]
        sys.modules[urlconf.__name__] = urlconf
        try:
            assert (
                reverse("admin_select_filter:options", urlconf=urlconf.__name__)
                == "/custom/"
            )
        finally:
            del sys.modules[urlconf.__name__]
