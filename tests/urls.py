from django.contrib import admin
from django.urls import include, path

from tests.testapp.admin import e2e_admin_site

urlpatterns = [
    path("admin/select-filter/", include("django_admin_select_filter.urls")),
    path("e2e-admin/", e2e_admin_site.urls),
    path("admin/", admin.site.urls),
]
