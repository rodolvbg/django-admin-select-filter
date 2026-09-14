from django.urls import path

from django_admin_select_filter.views import Select2FilterOptionsView

app_name = "admin_select_filter"

urlpatterns = [
    path("options/", Select2FilterOptionsView.as_view(), name="options"),
]
