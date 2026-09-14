from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/select-filter/", include("django_admin_select_filter.urls")),
    path("admin/", admin.site.urls),
]
