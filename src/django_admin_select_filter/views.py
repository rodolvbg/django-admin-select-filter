from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from django.apps import apps
from django.contrib.admin.sites import AdminSite, all_sites
from django.http import JsonResponse
from django.views import View

from django_admin_select_filter.filters import BaseSelectFilter

if TYPE_CHECKING:
    from typing import Any, ClassVar

    from django.contrib import admin
    from django.http import HttpRequest

AsyncFilterRegistry = dict[
    AdminSite, dict[str, dict[str, dict[str, type[BaseSelectFilter]]]]
]


class Select2FilterOptionsView(View):
    """Serve Select2 options for an asynchronous filter over AJAX."""

    #: When true, resolve the matching filter from the cached registry built
    #: by :meth:`_build_async_filter_registry` instead of scanning every
    #: registered ``AdminSite`` and calling ``get_list_filter()`` on each of
    #: its ``ModelAdmin``\ s on every request. Enable it by passing
    #: ``as_view_kwargs={"use_registry": True}`` to
    #: ``django_admin_select_filter_path()`` (or ``use_registry=True``
    #: directly to ``as_view()``).
    use_registry: ClassVar[bool] = False

    @staticmethod
    @functools.cache
    def _build_async_filter_registry() -> AsyncFilterRegistry:
        """Map every ``async_call`` filter across every registered ``AdminSite``.

        Shaped as ``{site: {app_label: {model_name: {parameter_name: filter}}}}``
        so :meth:`_find_admin_site_via_registry` can look one up in constant
        time instead of calling ``get_list_filter()`` on every registered
        ``ModelAdmin`` for every request.

        A ``staticmethod`` (rather than an instance method) so
        ``functools.cache`` can actually cache it: Django's ``View``
        instantiates a fresh instance per request, so caching on ``self``
        would never hit.

        Cached for the process's lifetime: admin registrations are static
        after Django startup. Call
        ``Select2FilterOptionsView._build_async_filter_registry.cache_clear()``
        to force a rebuild (mainly useful in tests that register admins
        dynamically). ``get_list_filter()`` is called with ``request=None``
        while building this, so an override that depends on the request
        isn't supported when ``use_registry`` is enabled.
        """
        registry: AsyncFilterRegistry = {}
        for site in all_sites:
            for model, model_admin in site._registry.items():
                for configured_filter in model_admin.get_list_filter(None):  # type: ignore[arg-type]
                    filter_class: Any = (
                        configured_filter[1]
                        if isinstance(configured_filter, (list, tuple))
                        else configured_filter
                    )
                    if not (
                        isinstance(filter_class, type)
                        and issubclass(filter_class, BaseSelectFilter)
                    ):
                        continue
                    if not (filter_class.async_call and filter_class.parameter_name):
                        continue
                    parameter_name = filter_class.parameter_name
                    app_label = model._meta.app_label
                    model_name = model._meta.model_name
                    assert app_label is not None
                    assert model_name is not None
                    parameter_map = (
                        registry.setdefault(site, {})
                        .setdefault(app_label, {})
                        .setdefault(model_name, {})
                    )
                    parameter_map[parameter_name] = filter_class
        return registry

    def get(self, request: HttpRequest) -> JsonResponse:
        """Return matching Select2 options as JSON for the requesting filter."""
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

        if model is None or not any(model in site._registry for site in all_sites):
            return JsonResponse(
                {"detail": "The requested admin model was not found."},
                status=404,
            )
        if not any(
            self._has_view_permission(site, model, request) for site in all_sites
        ):
            return JsonResponse({"detail": "Forbidden."}, status=403)

        find_admin_site = (
            self._find_admin_site_via_registry
            if self.use_registry
            else self._find_admin_site
        )
        admin_site = find_admin_site(model, request, parameter_name)
        if admin_site is None:
            return JsonResponse(
                {"detail": "The requested admin filter was not found."},
                status=404,
            )

        model_admin = admin_site._registry[model]
        filter_class = (
            self._build_async_filter_registry()
            .get(admin_site, {})
            .get(app_label, {})
            .get(model_name, {})
            .get(parameter_name)
            if self.use_registry
            else self._get_filter_class(model_admin, request, parameter_name)
        )
        assert filter_class is not None

        params = {key: request.GET.getlist(key) for key in request.GET}
        filter_instance = filter_class(request, params, model, model_admin)
        q = request.GET.get("q", "")
        options = filter_instance.get_async_options(request, q)
        return JsonResponse(
            {"results": [{"id": value, "text": text} for value, text in options]}
        )

    def _has_view_permission(
        self,
        site: AdminSite,
        model: type[Any],
        request: HttpRequest,
    ) -> bool:
        """Return whether ``site`` registers ``model`` with view permission granted."""
        model_admin = site._registry.get(model)
        return model_admin is not None and model_admin.has_view_permission(request)

    def _find_admin_site(
        self,
        model: type[Any],
        request: HttpRequest,
        parameter_name: str,
    ) -> AdminSite | None:
        """Return the registered ``AdminSite`` usable for this request, if any.

        Searches every registered ``AdminSite`` (not just the default
        ``django.contrib.admin.site``, so a project's own ``AdminSite`` works
        too) for one where ``model`` is registered, the request has view
        permission, and its ``ModelAdmin`` configures a matching async filter
        for ``parameter_name``.
        """
        for site in all_sites:
            if not self._has_view_permission(site, model, request):
                continue
            model_admin = site._registry[model]
            if self._get_filter_class(model_admin, request, parameter_name):
                return site
        return None

    def _find_admin_site_via_registry(
        self,
        model: type[Any],
        request: HttpRequest,
        parameter_name: str,
    ) -> AdminSite | None:
        """Same contract as :meth:`_find_admin_site`, backed by the cached
        registry from :meth:`_build_async_filter_registry` instead of
        calling ``get_list_filter()`` per site on every request.
        """
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        registry = self._build_async_filter_registry()
        for site in all_sites:
            if not self._has_view_permission(site, model, request):
                continue
            filter_class = (
                registry.get(site, {})
                .get(app_label, {})
                .get(model_name, {})
                .get(parameter_name)
            )
            if filter_class is not None:
                return site
        return None

    def _get_filter_class(
        self,
        model_admin: admin.ModelAdmin[Any],
        request: HttpRequest,
        parameter_name: str,
    ) -> type[BaseSelectFilter] | None:
        """Return the configured async filter matching ``parameter_name``, if any."""
        for configured_filter in model_admin.get_list_filter(request):
            filter_class: Any = (
                configured_filter[1]
                if isinstance(configured_filter, (list, tuple))
                else configured_filter
            )
            if (
                isinstance(filter_class, type)
                and issubclass(filter_class, BaseSelectFilter)
                and filter_class.async_call
                and filter_class.parameter_name == parameter_name
            ):
                return filter_class
        return None
