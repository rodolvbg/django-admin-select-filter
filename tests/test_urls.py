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
        urlconf = types.ModuleType("temp_urlconf")
        urlconf.urlpatterns = [django_admin_select_filter_path(route="custom/")]

        assert reverse("admin_select_filter:options", urlconf=urlconf) == "/custom/"
