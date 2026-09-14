from django.urls import path

from .views import Select2FilterOptionsView

app_name = "admin_select_filter"

urlpatterns = [
    path("options/", Select2FilterOptionsView.as_view(), name="options"),
]
