from __future__ import annotations

from typing import Any

from django.apps import apps
from django.contrib import admin
from django.http import Http404, HttpRequest, JsonResponse
from django.views import View

from django_admin_select_filter.filters import ForeignKeyFilter


class Select2FilterOptionsView(View):
    """Serve Select2 options for an asynchronous ``ForeignKeyFilter`` over AJAX."""

    def get(self, request: HttpRequest) -> JsonResponse:
        app_label = request.GET.get("app_label")
        model_name = request.GET.get("model_name")
        parameter_name = request.GET.get("parameter_name")
        if not (app_label and model_name and parameter_name):
            raise Http404
        model_admin = self._get_model_admin(app_label, model_name)
        filter_instance = self._build_filter(request, model_admin, parameter_name)
        q = request.GET.get("q", "")
        options = filter_instance.get_async_options(request, q)
        return JsonResponse(
            {"results": [{"id": value, "text": text} for value, text in options]}
        )

    @staticmethod
    def _get_model_admin(app_label: str, model_name: str) -> admin.ModelAdmin[Any]:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError as exc:
            raise Http404 from exc
        try:
            return admin.site._registry[model]
        except KeyError as exc:
            raise Http404 from exc

    @staticmethod
    def _build_filter(
        request: HttpRequest,
        model_admin: admin.ModelAdmin[Any],
        parameter_name: str,
    ) -> ForeignKeyFilter:
        for filter_class in model_admin.get_list_filter(request):
            if (
                isinstance(filter_class, type)
                and issubclass(filter_class, ForeignKeyFilter)
                and filter_class.parameter_name == parameter_name
            ):
                return filter_class(
                    request,
                    dict(request.GET.lists()),
                    model_admin.model,
                    model_admin,
                )
        raise Http404
