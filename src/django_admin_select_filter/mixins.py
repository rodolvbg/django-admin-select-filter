"""The features of the select filters, one mixin each: its options, its
part of the filtering and its part of ``media`` (the script it needs, only
when it's on). :class:`~django_admin_select_filter.filters.BaseSelectFilter`
puts them together; each one's options stay on it as they always were
(``multiple = True``, ``async_call = True``…).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.admin.filters import SimpleListFilter
from django.db import models
from django.forms import Media
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

if TYPE_CHECKING:
    from typing import Any, ClassVar

    from django.contrib.admin import ModelAdmin
    from django.http import HttpRequest

    from django_admin_select_filter.types import Choices

# The default ``name`` django_admin_select_filter_path() registers its route
# under. Declared here (rather than alongside it) so filters and urls.py
# share one source of truth without a circular import — urls.py already
# depends on views.py, which depends on the filters.
ASYNC_CALL_URL_NAME = "options"


def _csp_nonce(request: HttpRequest | None) -> str | None:
    """Return the request's CSP nonce as a plain string, or ``None``.

    Django's own CSP middleware (6.0+) keeps it in ``request._csp_nonce``
    (read through ``django.middleware.csp.get_nonce()``), the third-party
    ``django-csp`` package in ``request.csp_nonce``: this picks up either
    without a dependency on which one (or neither) a project uses.

    Not ``if nonce``: Django's own ``LazyNonce`` evaluates falsy until first
    accessed elsewhere, even though converting it here would happily
    generate one (and add it to the policy's header) — only its absence
    (a plain ``None``) means no CSP nonce support is active at all.
    """
    nonce = getattr(request, "csp_nonce", None)
    if nonce is None:
        nonce = getattr(request, "_csp_nonce", None)
    return str(nonce) if nonce is not None else None


def _module_script(path: str, request: HttpRequest | None) -> Any:
    """Render ``path`` as an ES module ``<script>`` tag for use in a ``Media.js`` list.

    Adds a CSP nonce attribute when the request has one (see
    :func:`_csp_nonce`) — needed for a ``script-src`` policy that only
    allows nonced scripts. A policy allowing the static files' origin
    (``'self'``) needs none: the package renders no inline script.

    ``django.forms.Script`` could build this ``<script>`` natively with a
    ``type="module"`` attribute, but only from Django 5.2 on; this package
    supports Django >= 4.2, so it renders the tag itself instead, via the
    same ``__html__`` escape hatch ``Media.render_js()`` has always deferred
    to when present rather than building the tag itself — this works
    uniformly back to 4.2.

    Returns ``Any`` rather than a precise type: django-stubs types
    ``Media.js`` as ``Sequence[str] | None``, not accounting for a
    ``SafeString``'s ``__html__()`` being used this way.
    """
    nonce = _csp_nonce(request)
    nonce_attr = f' nonce="{nonce}"' if nonce else ""
    return mark_safe(
        f'<script type="module"{nonce_attr} src="{static(path)}"></script>'
    )


class SelectFilterFeature(SimpleListFilter):
    """What every feature shares: the filter's request and admin, its
    reserved values, and the hooks the features add their part through.

    Its annotations name the options other features read (``async_call``
    on the null option, ``multiple`` on the async options…): each one's
    value is on its own mixin."""

    #: Reserved values: the "All" option and the empty-value option. They
    #: can be overridden if they conflict with valid values.
    all_value: ClassVar[str] = "__all__"
    null_value: ClassVar[str] = "__null__"
    #: The query string's parameter (``?author=3``): it names the filter in
    #: the URL, and the async options' endpoint finds it by it.
    parameter_name: str | None = None
    #: The lookup it filters by, when it isn't ``parameter_name``
    #: (``"author__country"`` for ``?country=3``).
    field_name: str | None = None

    request: HttpRequest
    model_admin: ModelAdmin[Any]
    model_admin_queryset: models.QuerySet[Any]
    filter_only_used_values: ClassVar[bool]
    async_call: ClassVar[bool]
    multiple: ClassVar[bool]

    @property
    def field_lookup(self) -> str | None:
        """What it filters by: ``field_name``, else ``parameter_name``."""
        return self.field_name or self.parameter_name

    @property
    def media(self) -> Media:
        """Each feature adds its scripts to its ``super()``'s."""
        return Media()

    def _module_script(self, path: str) -> Any:
        return _module_script(path, getattr(self, "request", None))

    def _option_items(
        self,
        request: HttpRequest | None = None,
        q: str = "",
    ) -> Choices:
        """Return every available option as ``(key, label)`` string pairs."""
        raise NotImplementedError

    #: A template for each option (``value``, ``label``, ``obj``, ``data`` and
    #: ``filter``), shown as it renders in the list and as the selection;
    #: none: its label.
    option_template: ClassVar[str | None] = None

    def get_option_data(
        self, value: str, label: str, obj: Any = None
    ) -> dict[str, Any] | None:
        """More of an option, for the page: anything JSON can carry, the
        package doesn't read it (``obj``: a ``ForeignKeyFilter``'s object).
        None: nothing more."""
        return None

    def _remember_option(self, value: str, label: str, obj: Any = None) -> None:
        """Keep an option's data (``get_option_data()``) and its template's
        HTML (``option_template``), for its ``<option>`` and its API result."""
        extra: dict[str, Any] = {}
        data = self.get_option_data(value, label, obj)
        if data:
            extra["data"] = data
        if self.option_template:
            extra["html"] = render_to_string(
                self.option_template,
                {
                    "filter": self,
                    "value": value,
                    "label": label,
                    "obj": obj,
                    "data": data or {},
                },
                request=getattr(self, "request", None),
            )
        if extra:
            self.__dict__.setdefault("_option_extras", {})[value] = extra

    def option_extra(self, value: str) -> dict[str, Any]:
        """An option's ``data`` and ``html``, those it has."""
        return dict(self.__dict__.get("_option_extras", {}).get(str(value), {}))

    def _selected_option_items(self) -> Choices:
        """Return only the currently selected options, as ``(key, label)`` pairs."""
        raise NotImplementedError

    def selected_values(self) -> list[str]:
        """Return the selected raw value, in a list. Empty when nothing is
        selected."""
        value = self.value()
        return [value] if value else []

    def value_condition(self, value: str) -> models.Q:
        """The lookup of one selected value."""
        return models.Q(**{self.field_lookup or "": value})

    def values_condition(self, values: list[str]) -> models.Q:
        """The lookup of the selected values."""
        return self.value_condition(values[0])

    def initial_options(self, request: HttpRequest) -> Choices:
        """The options Django's list-filter template renders at first."""
        return self._option_items()

    def leading_async_options(self) -> Choices:
        """What the async options start with: "All"."""
        return [(self.all_value, gettext("All"))]

    def extend_async_options(self, request: HttpRequest, options: Choices) -> Choices:
        """What the async options end with (the empty-value option)."""
        return options


class UsedValuesMixin(SelectFilterFeature):
    """``filter_only_used_values``: offer only the values the changelist's
    rows use (the relations already present in the ``ModelAdmin``'s
    queryset). It defaults to true."""

    filter_only_used_values: ClassVar[bool] = True

    def used_values(self) -> models.QuerySet[Any]:
        """The values of ``field_lookup`` the changelist's rows use."""
        return self.model_admin_queryset.values_list(self.field_lookup or "", flat=True)


class NullOptionMixin(SelectFilterFeature):
    """The empty-value option ("-"), filtering by ``__isnull``.

    ``nullable``
        Controls whether the empty-value option is available. When left as
        ``None``, the value is inferred from the configured model field.
    ``null_label``
        Text of the empty-value option. When left as ``None``, the admin's
        own empty value display is used (``ModelAdmin.empty_value_display``,
        ``"-"`` by default), as Django's list filters do. Override
        ``get_null_label(request)`` to choose it per request.
    """

    nullable: bool | None = None
    null_label: ClassVar[Any] = None

    def __init__(
        self,
        request: HttpRequest,
        params: dict[str, Any],
        admin_model: type[models.Model],
        model_admin: ModelAdmin[Any],
    ) -> None:
        if self.nullable is None:
            self.nullable = self._is_nullable(admin_model)
        self.has_null_option = (
            not self.async_call or not self.filter_only_used_values
        ) and self._has_null_option()
        super().__init__(request, params, admin_model, model_admin)

    def get_null_label(self, request: HttpRequest | None) -> str:
        """Text of the empty-value option: ``null_label``, else the admin's
        empty value display (``"-"`` by default)."""
        if self.null_label is not None:
            return str(self.null_label)
        get_empty_value_display = getattr(
            getattr(self, "model_admin", None), "get_empty_value_display", None
        )
        return (
            str(get_empty_value_display()) if callable(get_empty_value_display) else "-"
        )

    @property
    def null_label_display(self) -> str:
        """The empty-value option's text for the changelist request."""
        return self.get_null_label(getattr(self, "request", None))

    def _is_nullable(self, admin_model: type[models.Model]) -> bool:
        """Determine whether the configured field accepts null values."""
        for field in admin_model._meta.get_fields():
            if self.field_lookup in (field.name, getattr(field, "attname", None)):
                return bool(getattr(field, "null", False))
        return False

    def _has_null_option(self) -> bool:
        """Return whether the filter should expose its null-value option."""
        if not self.nullable or self.field_lookup is None:
            return False
        if not self.filter_only_used_values:
            return True
        return self.model_admin_queryset.filter(
            **{f"{self.field_lookup}__isnull": True}
        ).exists()

    def value_condition(self, value: str) -> models.Q:
        if value == self.null_value:
            return models.Q(**{f"{self.field_lookup}__isnull": True})
        return super().value_condition(value)

    def initial_options(self, request: HttpRequest) -> Choices:
        options = super().initial_options(request)
        if self.has_null_option:
            options.append((self.null_value, self.get_null_label(request)))
        return options

    def extend_async_options(self, request: HttpRequest, options: Choices) -> Choices:
        options = super().extend_async_options(request, options)
        if self._has_null_option():
            options.append((self.null_value, self.get_null_label(request)))
        return options


class MultipleValuesMixin(SelectFilterFeature):
    """Several values at once.

    ``multiple``
        When true, the Select2 widget accepts several values at once and
        ``queryset()`` filters with an ``__in`` lookup. Selected values are
        stored in the query string joined by ``multiple_separator``, so
        configured values (primary keys, option values) must not contain it.
        It defaults to false.
    ``multiple_separator``
        Character joining multiple selected values in the query string. It
        defaults to ``","``.
    """

    multiple: ClassVar[bool] = False
    multiple_separator: ClassVar[str] = ","

    @property
    def media(self) -> Media:
        media = super().media
        if self.multiple:
            media += Media(
                js=[
                    self._module_script("admin_select_filter/js/multiple_navigation.js")
                ]
            )
        return media

    def selected_values(self) -> list[str]:
        """Return the selected raw values, splitting on ``multiple_separator``
        when ``multiple`` is enabled. Empty when nothing is selected."""
        if not self.multiple:
            return super().selected_values()
        value = self.value()
        if not value:
            return []
        return [item for item in value.split(self.multiple_separator) if item]

    def values_condition(self, values: list[str]) -> models.Q:
        if not self.multiple:
            return super().values_condition(values)
        real_values = [value for value in values if value != self.null_value]
        condition = models.Q()
        if real_values:
            condition |= models.Q(**{f"{self.field_lookup}__in": real_values})
        if self.null_value in values:
            condition |= self.value_condition(self.null_value)
        return condition

    def leading_async_options(self) -> Choices:
        # No "All": clearing every selected value already means no filter.
        return [] if self.multiple else super().leading_async_options()


class SearchableMixin(SelectFilterFeature):
    """``searchable``: when false, hide Select2's search input and behave
    like a plain dropdown. Best for a short, static option list. It
    defaults to true."""

    searchable: ClassVar[bool] = True

    @property
    def media(self) -> Media:
        media = super().media
        if not self.searchable:
            media += Media(
                js=[self._module_script("admin_select_filter/js/non_searchable.js")]
            )
        return media


class AsyncOptionsMixin(SelectFilterFeature):
    """Options loaded as Select2 asks for them, through an API.

    ``async_call``
        When true, defer loading options until Select2 requests them through
        the API. It defaults to false.
    ``async_call_url``
        URL the Select2 widget's JS fetches options from when ``async_call``
        is true. Left as ``None`` (the default), it resolves to
        ``reverse(f"admin_select_filter:{ASYNC_CALL_URL_NAME}")`` — the
        shared endpoint registered via ``django_admin_select_filter_path()``.
        ``reverse()`` is what makes this work correctly regardless of the
        admin page the filter is rendered on and wherever that route is
        actually mounted — a bare path segment like ``"options/"`` would
        resolve relative to the *current page*, not that mount point, and
        silently hit the wrong URL. If you pass a custom ``name=`` to
        ``django_admin_select_filter_path()``, set ``async_call_url``
        explicitly on every ``async_call`` filter to match — there's no way
        for a filter to otherwise discover which name was used for the
        specific route it should call. Also set it explicitly to point a
        filter at a genuinely different, custom view.
    """

    async_call: ClassVar[bool] = False
    async_call_url: str | None = None

    def __init__(
        self,
        request: HttpRequest,
        params: dict[str, Any],
        admin_model: type[models.Model],
        model_admin: ModelAdmin[Any],
    ) -> None:
        if self.async_call and self.async_call_url is None:
            self.async_call_url = reverse(f"admin_select_filter:{ASYNC_CALL_URL_NAME}")
        super().__init__(request, params, admin_model, model_admin)

    @property
    def media(self) -> Media:
        media = super().media
        if self.async_call:
            media += Media(
                js=[self._module_script("admin_select_filter/js/async_options.js")]
            )
        return media

    def has_output(self) -> bool:
        """Keep asynchronous filters visible before their options are loaded."""
        return self.async_call or super().has_output()

    def initial_options(self, request: HttpRequest) -> Choices:
        # Asynchronous: only the selected ones, the rest come from the API.
        if self.async_call:
            return self._selected_option_items()
        return super().initial_options(request)

    def _get_option_facet_counts(self) -> dict[str, int]:
        """Count options for either filter presentation.

        Asynchronous filters use these counts in their API results. Synchronous
        filters may reuse the helper, although Django's standard list-filter
        rendering already calculates its own facet counts.
        """
        if self.field_lookup is None:
            return {}
        counts = (
            self.model_admin_queryset.order_by()
            .values(self.field_lookup)
            .annotate(count=models.Count("pk"))
        )
        return {
            self.null_value if value is None else str(value): count
            for value, count in counts.values_list(self.field_lookup, "count")
        }

    def _build_async_options(
        self,
        request: HttpRequest,
        items: Choices,
    ) -> Choices:
        """Assemble the "All"/items/null options, applying facet counts if asked.

        The "All" option is skipped when ``multiple`` is enabled: clearing
        every selected value already means "no filter" for a multi-select.
        """
        options = self.extend_async_options(
            request, [*self.leading_async_options(), *items]
        )
        if request.GET.get("facets") == "true":
            facet_counts = self._get_option_facet_counts()
            options = [
                (
                    value,
                    label
                    if value == self.all_value
                    else f"{label} ({facet_counts.get(value, 0)})",
                )
                for value, label in options
            ]
        return options

    def get_async_options(
        self,
        request: HttpRequest,
        q: str,
    ) -> Choices:
        """Return Select2 options for an API request and its search term."""
        return self._build_async_options(
            request, self._option_items(request=request, q=q)
        )
