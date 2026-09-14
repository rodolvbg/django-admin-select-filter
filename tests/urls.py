from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin/select-filter/", include("django_admin_select_filter.urls")),
]
