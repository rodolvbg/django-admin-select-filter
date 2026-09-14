from __future__ import annotations

from typing import Any

from django.apps import apps
from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.views import View

from django_admin_select_filter.filters import ForeignKeyFilter


def _get_filter_class(
    model_admin: admin.ModelAdmin[Any],
    request: HttpRequest,
    parameter_name: str,
) -> type[ForeignKeyFilter] | None:
    for configured_filter in model_admin.get_list_filter(request):
        filter_class: Any = (
            configured_filter[1]
            if isinstance(configured_filter, (list, tuple))
            else configured_filter
        )
        if (
            isinstance(filter_class, type)
            and issubclass(filter_class, ForeignKeyFilter)
            and filter_class.async_call
            and filter_class.parameter_name == parameter_name
        ):
            return filter_class
    return None


class Select2FilterOptionsView(View):
    """Serve Select2 options for an asynchronous ``ForeignKeyFilter`` over AJAX."""

    def get(self, request: HttpRequest) -> JsonResponse:
        app_label = request.GET.get("app_label")
        model_name = request.GET.get("model_name")
        parameter_name = request.GET.get("parameter_name")
        if not (app_label and model_name and parameter_name):
            return JsonResponse(
                {"detail": "app_label, model_name and parameter_name are required."},
                status=400,
            )

        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            model = None
        model_admin = admin.site._registry.get(model) if model is not None else None
        if model is None or model_admin is None:
            return JsonResponse(
                {"detail": "The requested admin model was not found."},
                status=404,
            )
        if not model_admin.has_view_permission(request):
            return JsonResponse({"detail": "Forbidden."}, status=403)

        filter_class = _get_filter_class(model_admin, request, parameter_name)
        if filter_class is None:
            return JsonResponse(
                {"detail": "The requested admin filter was not found."},
                status=404,
            )

        params = {key: request.GET.getlist(key) for key in request.GET}
        filter_instance = filter_class(request, params, model, model_admin)
        q = request.GET.get("q", "")
        options = filter_instance.get_async_options(request, q)
        return JsonResponse(
            {"results": [{"id": value, "text": text} for value, text in options]}
        )
