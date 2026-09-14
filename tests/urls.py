from django.contrib import admin
from django.urls import path

from django_admin_select_filter.urls import django_admin_select_filter_path
from tests.testapp.admin import e2e_admin_site

urlpatterns = [
    django_admin_select_filter_path(),
    path("e2e-admin/", e2e_admin_site.urls),
    path("admin/", admin.site.urls),
]
