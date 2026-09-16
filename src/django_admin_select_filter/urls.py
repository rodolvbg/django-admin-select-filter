from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import include, path

from django_admin_select_filter.filters import ASYNC_CALL_URL_NAME
from django_admin_select_filter.views import Select2FilterOptionsView

if TYPE_CHECKING:
    from typing import Any

    from django.urls import URLResolver


def django_admin_select_filter_path(
    route: str = "django_admin_select_filter/options/",
    view: type[Select2FilterOptionsView] = Select2FilterOptionsView,
    name: str = ASYNC_CALL_URL_NAME,
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

    If you pass a custom ``name``, every ``async_call`` filter must set its
    own ``async_call_url`` to match: filters resolve the default endpoint via
    ``django_admin_select_filter.filters.ASYNC_CALL_URL_NAME``, and have no
    way to discover a ``name`` chosen here at a different call site.

    Pass ``as_view_kwargs={"use_registry": True}`` to have the view resolve
    filters from a cached, prebuilt lookup instead of scanning every
    registered ``AdminSite`` on each request — see
    ``Select2FilterOptionsView.use_registry``.
    """
    view_func = view.as_view(**(as_view_kwargs or {}))
    return path(
        route,
        include(([path("", view_func, name=name)], "admin_select_filter")),
    )
