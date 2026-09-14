from __future__ import annotations

from typing import Any

from django.urls import URLResolver, include, path

from django_admin_select_filter.views import Select2FilterOptionsView


def django_admin_select_filter_path(
    route: str = "django_admin_select_filter/options/",
    view: type[Select2FilterOptionsView] = Select2FilterOptionsView,
    name: str = "options",
    as_view_kwargs: dict[str, Any] | None = None,
) -> URLResolver:
    """Return a ``urlpatterns`` entry serving the Select2 options endpoint.

    Drop this directly into your project's root ``urlpatterns`` — no
    ``include()`` needed::

        from django_admin_select_filter.urls import django_admin_select_filter_path

        urlpatterns = [
            django_admin_select_filter_path(),
            ...
        ]

    The endpoint stays reversible as ``admin_select_filter:options`` (or
    ``f"admin_select_filter:{name}"`` if you pass a custom ``name``) — it's
    still namespaced internally via ``include()``, that's just no longer
    something the caller has to write.
    """
    view_func = view.as_view(**(as_view_kwargs or {}))
    return path(
        route,
        include(([path("", view_func, name=name)], "admin_select_filter")),
    )
