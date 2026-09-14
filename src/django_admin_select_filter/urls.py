from django.conf import settings
from django.urls import path

from django_admin_select_filter.constants import DEFAULT_ASYNC_CALL_URL
from django_admin_select_filter.views import Select2FilterOptionsView

app_name = "admin_select_filter"

DJANGO_ADMIN_SELECT_FILTERS_ASYNC_CALL_URL = getattr(
    settings, "DJANGO_ADMIN_SELECT_FILTERS_ASYNC_CALL_URL", DEFAULT_ASYNC_CALL_URL
)

urlpatterns = [
    path(
        DJANGO_ADMIN_SELECT_FILTERS_ASYNC_CALL_URL,
        Select2FilterOptionsView.as_view(),
        name="options",
    ),
]
