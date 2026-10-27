from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from django.apps import apps
from django.contrib.admin.widgets import get_select2_language
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models
from django.forms import Media
from django.templatetags.static import static
from django.urls import reverse
from django.utils.functional import cached_property

from django_admin_select_filter.mixins import (
    ASYNC_CALL_URL_NAME,
    AsyncOptionsMixin,
    MultipleValuesMixin,
    NullOptionMixin,
    SearchableMixin,
    UsedValuesMixin,
)

__all__ = [
    "ASYNC_CALL_URL_NAME",  # Where it always was (it's the mixins' now).
    "BaseSelectFilter",
    "ChoiceFilter",
    "ForeignKeyFilter",
    "field_list_filter",
]

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any, ClassVar

    from django.contrib.admin import ModelAdmin
    from django.http import HttpRequest

    from django_admin_select_filter.types import Choices


class BaseSelectFilter(
    UsedValuesMixin,
    NullOptionMixin,
    MultipleValuesMixin,
    SearchableMixin,
    AsyncOptionsMixin,
):
    """Shared plumbing for the project's Select2-powered admin list filters.

    Handles everything that doesn't depend on where the options come from:
    queryset filtering by the raw lookup value, and the Select2 template's
    ``choices()`` rendering. Subclasses only need to supply the available
    options (see ``get_options``, ``get_async_options`` and ``lookups`` on
    :class:`ForeignKeyFilter` and :class:`ChoiceFilter` for the two
    supported shapes).

    Each feature is a mixin of its own (``django_admin_select_filter.mixins``),
    with its options, its part of the filtering and of ``media``:

    - ``filter_only_used_values`` (:class:`UsedValuesMixin`): only the
      values already in use.
    - ``nullable``, ``null_label`` (:class:`NullOptionMixin`): the
      empty-value option.
    - ``multiple``, ``multiple_separator`` (:class:`MultipleValuesMixin`):
      several values at once.
    - ``searchable`` (:class:`SearchableMixin`): Select2's search input.
    - ``async_call``, ``async_call_url`` (:class:`AsyncOptionsMixin`):
      options loaded through an API.

    And its own:

    ``parameter_name``
        The URL's parameter (``?group=3``), and, without ``field_name``, the
        lookup applied to the changelist queryset, such as ``"group"`` or
        ``"groups"``. Required.
    ``field_name``
        The lookup applied to the changelist queryset when it isn't
        ``parameter_name``: ``parameter_name = "country"`` with
        ``field_name = "author__country"`` filters by the author's country
        as ``?country=3``. The field (its choices, its related model, its
        nullability) is found by it.
    ``title``
        Label shown by Django above the filter. By default it uses the related
        model admin's plural verbose name.
    ``theme``
        Select2 theme; ``None`` picks one for the admin (see
        ``select2_theme``).
    """

    #: Select2 theme; ``None`` picks one for the admin (see ``select2_theme``).
    theme: ClassVar[str | None] = None
    title: Any | None = None

    def __init__(
        self,
        request: HttpRequest,
        params: dict[str, Any],
        admin_model: type[models.Model],
        model_admin: ModelAdmin[Any],
    ) -> None:
        """Configure the filter for an admin changelist request."""
        self.request = request
        self.model_admin = model_admin
        self.admin_app_label = admin_model._meta.app_label
        self.admin_model_name = admin_model._meta.model_name
        self.facets = self.request.GET.get("_facets") == "True"
        super().__init__(request, params, admin_model, model_admin)

    @cached_property
    def model_admin_queryset(self) -> models.QuerySet[Any]:  # type: ignore[override]
        """Return and cache the source ModelAdmin queryset when first needed."""
        return self.model_admin.get_queryset(self.request)

    @property
    def select2_language(self) -> str | None:
        """Select2 language code for the active language, if Select2 has one."""
        return get_select2_language()

    @property
    def select2_theme(self) -> str | None:
        """``theme``, or with django-unfold its styled "admin-autocomplete"
        (the theme of the admin's autocomplete widgets); else Select2's
        default, styled by this package."""
        if self.theme:
            return self.theme
        return "admin-autocomplete" if apps.is_installed("unfold") else None

    @property
    def select2_i18n_url(self) -> str | None:
        """Select2's translations for the active language (the same file the
        admin's autocomplete widgets load), so its messages — "No results
        found", "Searching…" — follow the admin's language."""
        language = self.select2_language
        return (
            static(f"admin/js/vendor/select2/i18n/{language}.js") if language else None
        )

    @property
    def media(self) -> Media:
        """Static assets this filter's template needs: Select2's, then each
        feature's script when it's on (``async_call``, non-``searchable``,
        ``multiple``: see the mixins) — mirroring ``ModelAdmin.media``'s own
        pattern of a ``@property`` computing a ``Media`` instance from
        instance state, rather than a static inner ``class Media``.

        Access ``{{ spec.media.css }}``/``{{ spec.media.js }}`` separately in
        a template (as Django's own admin templates do), since ``Media``
        resolves ``.css``/``.js`` through ``__getitem__`` rather than a real
        attribute — plain attribute access isn't available.

        Each ``<script>`` picks up a CSP nonce when the request has one —
        from Django's own CSP middleware (6.0+) or the third-party
        ``django-csp`` package; harmless to skip when neither is in use.
        All of them are external files: nothing inline for a Content
        Security Policy to block.
        """
        css = ["admin/css/vendor/select2/select2.css"]
        if self.select2_theme == "admin-autocomplete":
            # The layout of the admin's autocomplete widgets.
            css.append("admin/css/autocomplete.css")
        css.append("admin_select_filter/css/admin_select2_filter.css")
        core = Media(
            css={"all": css},
            js=[self._module_script("admin_select_filter/js/core.js")],
        )
        return core + super().media

    def _resolve_field(self, admin_model: type[models.Model]) -> Any | None:
        """Walk ``field_lookup`` across relations and return its final field.

        Handles a nested lookup, such as ``"publisher__country"``, by
        following each ``__``-separated segment's relation in turn — forward
        or reverse — except the last, whose field is returned as-is. Returns
        ``None`` when ``field_lookup`` is unset or any segment doesn't
        resolve to a real field.
        """
        if self.field_lookup is None:
            return None
        current_model: type[models.Model] = admin_model
        parts = self.field_lookup.split("__")
        for part in parts[:-1]:
            try:
                field = current_model._meta.get_field(part)
            except FieldDoesNotExist:
                return None
            related_model = getattr(field, "related_model", None)
            if related_model is None:
                return None
            current_model = related_model
        try:
            return current_model._meta.get_field(parts[-1])
        except FieldDoesNotExist:
            return None

    def queryset(
        self,
        request: HttpRequest,
        queryset: models.QuerySet[Any],
    ) -> models.QuerySet[Any]:
        """Apply the selected value(s) or the null lookup to the changelist queryset."""
        if self.field_lookup is None:
            return queryset
        values = self.selected_values()
        if not values:
            return queryset
        return queryset.filter(self.values_condition(values))

    def choices(self, changelist: Any) -> Iterator[dict[str, Any]]:  # type: ignore[override]
        """Yield Django choices with the raw lookup key required by Select2.

        ``selected`` is recomputed against :meth:`selected_values` rather than
        Django's own single-value comparison, so it stays correct when
        ``multiple`` is enabled and several values are selected at once.
        """
        selected_values = self.selected_values()
        for index, choice in enumerate(super().choices(changelist)):
            key = "" if index == 0 else str(self.lookup_choices[index - 1][0])
            selected = not selected_values if index == 0 else key in selected_values
            yield {**choice, "key": key, "selected": selected}

    def lookups(
        self,
        request: HttpRequest,
        model_admin: ModelAdmin[Any],
    ) -> Choices:
        """Return choices rendered initially by Django's list-filter template."""
        return self.initial_options(request)


class ForeignKeyFilter(BaseSelectFilter):
    """Filter an admin changelist by selectable related-model instances.

    Subclasses configure the filter through these class attributes:

    ``model``
        Related model whose instances become the available options. When left
        unset, it's inferred by walking the lookup (``field_name``, else
        ``parameter_name``) across the admin model's relations — including a
        nested lookup such as
        ``"publisher__country"`` — and taking the last relation's target
        model. Configure it explicitly when it can't be inferred (the lookup
        isn't a real relation chain) or to point elsewhere.
    ``ordering``
        Field names used to order the related instances.
    ``only``
        Related-model fields loaded by the options queryset. Include every
        field needed by the model's string representation.
    ``admin_autocomplete``
        When true, Select2 loads and searches the options from the admin's
        own autocomplete endpoint (``admin:autocomplete``, the one of
        ``autocomplete_fields``) — no ``django_admin_select_filter_path()``
        needed. The lookup (``field_name``, else ``parameter_name``) must end
        in a forward ``ForeignKey`` or ``ManyToManyField``, and the related
        model needs a ``ModelAdmin``
        with ``search_fields`` on the site. It searches every related object
        (``filter_only_used_values`` doesn't apply) and has no facet counts.
        It defaults to false.

    ``all_value`` and ``null_value`` are reserved values used by the async API
    for the translated “All” option and the null option, respectively. They can
    be overridden if those values conflict with valid primary keys.
    """

    template = "admin_select_filter/filters/foreign_key_filter.html"
    model: type[models.Model] | None = None
    ordering: ClassVar[list[str]] = []
    only: ClassVar[list[str]] = []
    admin_autocomplete: ClassVar[bool] = False
    #: With ``admin_autocomplete``: the relation field the admin's endpoint is
    #: asked about (``app_label``, ``model_name``, ``field_name``).
    autocomplete_source: dict[str, str] | None = None

    def __init__(
        self,
        request: HttpRequest,
        params: dict[str, Any],
        admin_model: type[models.Model],
        model_admin: ModelAdmin[Any],
    ) -> None:
        """Configure the filter for an admin changelist request."""
        if self.model is None:
            self.model = self._resolve_model(admin_model)
        if self.model is None:
            raise TypeError(
                f"{type(self).__name__}.model must be configured, or "
                f"{self.field_lookup!r} must resolve to a related model"
            )

        if self.title is None:
            registered_admin = model_admin.admin_site._registry.get(self.model)
            title_model = (
                registered_admin.model if registered_admin is not None else self.model
            )
            self.title = title_model._meta.verbose_name_plural
        if self.admin_autocomplete:
            self._use_admin_autocomplete(request, admin_model, model_admin)
        super().__init__(request, params, admin_model, model_admin)

    def _use_admin_autocomplete(
        self,
        request: HttpRequest,
        admin_model: type[models.Model],
        model_admin: ModelAdmin[Any],
    ) -> None:
        """Load the options from the admin's autocomplete endpoint."""
        assert self.model is not None
        field = self._resolve_field(admin_model)
        name = type(self).__name__
        if not isinstance(field, models.ForeignKey | models.ManyToManyField):
            raise ImproperlyConfigured(
                f"{name}.admin_autocomplete needs {self.field_lookup!r} to end "
                "in a ForeignKey or a ManyToManyField."
            )
        site = model_admin.admin_site
        related_admin = site._registry.get(self.model)
        if related_admin is None or not related_admin.get_search_fields(request):
            raise ImproperlyConfigured(
                f"{name}.admin_autocomplete needs a ModelAdmin with "
                f"search_fields for {self.model.__name__} on the "
                f"{site.name!r} admin site."
            )
        self.async_call = True  # type: ignore[misc]
        self.async_call_url = reverse(f"{site.name}:autocomplete")
        self.autocomplete_source = {
            "app_label": field.model._meta.app_label,
            "model_name": field.model._meta.model_name or "",
            "field_name": field.name,
        }

    def _resolve_model(
        self, admin_model: type[models.Model]
    ) -> type[models.Model] | None:
        """Return ``field_lookup``'s target model, following relations.

        Handles a nested lookup, such as ``"publisher__country"``, since it
        relies on :meth:`BaseSelectFilter._resolve_field` to walk each
        ``__``-separated segment's relation in turn — forward or reverse.
        """
        field = self._resolve_field(admin_model)
        if field is None:
            return None
        return getattr(field, "related_model", None)

    def get_options(
        self,
        request: HttpRequest | None = None,
        q: str = "",
    ) -> models.QuerySet[Any]:
        """Return allowed related instances, optionally searched with ``q``.

        The supplied request belongs to the API call. When it is omitted, the
        original admin changelist request stored on the filter is used.
        """
        assert self.model is not None
        queryset = self.model._default_manager.all()
        if self.filter_only_used_values and self.field_lookup is not None:
            queryset = queryset.filter(pk__in=self.used_values())
        if self.only:
            queryset = queryset.only(*self.only)
        if self.ordering:
            queryset = queryset.order_by(*self.ordering)
        related_admin = self.model_admin.admin_site._registry.get(self.model)
        if q and related_admin is not None:
            queryset, may_have_duplicates = related_admin.get_search_results(
                request or self.request,
                queryset,
                q,
            )
            if may_have_duplicates:
                queryset = queryset.distinct()
        return queryset

    def _option_items(
        self,
        request: HttpRequest | None = None,
        q: str = "",
    ) -> Choices:
        """Return every available option as ``(key, label)`` string pairs."""
        return [
            (str(instance.pk), str(instance))
            for instance in self.get_options(request=request, q=q)
        ]

    def _selected_option_items(self) -> Choices:
        """Return only the currently selected options, as ``(key, label)`` pairs."""
        assert self.model is not None
        selected_pks = [
            value for value in self.selected_values() if value != self.null_value
        ]
        selected_instances = (
            self.model._default_manager.filter(pk__in=selected_pks)
            if selected_pks
            else self.model._default_manager.none()
        )
        return [(str(instance.pk), str(instance)) for instance in selected_instances]


class ChoiceFilter(BaseSelectFilter):
    """Filter an admin changelist by scalar values, not tied to a relation.

    Unlike :class:`ForeignKeyFilter`, options aren't related-model instances —
    they're plain ``(value, label)`` pairs, which makes this usable for any
    field with discrete values: a ``ChoiceField``-backed ``CharField`` or
    ``IntegerField``, a ``BooleanField``, or any other lookup for which you
    can supply an explicit option list.

    Subclasses configure the filter through these class attributes:

    ``options``
        Explicit ``(value, label)`` pairs to offer. When left unset, options
        are read from the configured field's ``choices`` (e.g. a
        ``ChoiceField``); configuring this is required if the field has none.

    ``all_value`` and ``null_value`` are reserved values used by the async API
    for the translated “All” option and the null option, respectively. They can
    be overridden if those values conflict with valid option values.
    """

    template = "admin_select_filter/filters/choice_filter.html"
    options: list[tuple[Any, str]] | None = None

    def __init__(
        self,
        request: HttpRequest,
        params: dict[str, Any],
        admin_model: type[models.Model],
        model_admin: ModelAdmin[Any],
    ) -> None:
        """Configure the filter for an admin changelist request."""
        if self.parameter_name is None:
            raise TypeError(f"{type(self).__name__}.parameter_name must be configured")

        field = self._resolve_field(admin_model)
        if self.options is None:
            field_choices = getattr(field, "choices", None) if field else None
            if not field_choices:
                raise TypeError(
                    f"{type(self).__name__}.options must be configured, or "
                    f"{self.field_lookup!r} must name a field with choices"
                )
            self.options = [(value, str(label)) for value, label in field_choices]
        if self.title is None:
            self.title = field.verbose_name if field is not None else self.field_lookup
        super().__init__(request, params, admin_model, model_admin)

    def get_options(
        self,
        request: HttpRequest | None = None,
        q: str = "",
    ) -> list[tuple[Any, str]]:
        """Return allowed options, optionally searched with ``q``.

        The supplied request is accepted for parity with
        :meth:`ForeignKeyFilter.get_options` but isn't needed here, since
        matching happens in Python against the configured ``options``.
        """
        assert self.options is not None
        options = self.options
        if self.filter_only_used_values and self.field_lookup is not None:
            used_values = set(
                self.used_values().exclude(**{f"{self.field_lookup}__isnull": True})
            )
            options = [
                (value, label) for value, label in options if value in used_values
            ]
        if q:
            q_lower = q.lower()
            options = [
                (value, label) for value, label in options if q_lower in label.lower()
            ]
        return options

    def _option_items(
        self,
        request: HttpRequest | None = None,
        q: str = "",
    ) -> Choices:
        """Return every available option as ``(key, label)`` string pairs."""
        return [
            (str(value), label)
            for value, label in self.get_options(request=request, q=q)
        ]

    def _selected_option_items(self) -> Choices:
        """Return only the currently selected options, as ``(key, label)`` pairs."""
        assert self.options is not None
        selected_values = [
            value for value in self.selected_values() if value != self.null_value
        ]
        option_by_key = {str(value): label for value, label in self.options}
        return [
            (value, option_by_key[value])
            for value in selected_values
            if value in option_by_key
        ]


@functools.cache
def _bind_parameter_name(
    select_filter_class: type[BaseSelectFilter],
    parameter_name: str,
    field_name: str | None = None,
) -> type[BaseSelectFilter]:
    """Return (and cache) a ``select_filter_class`` subclass bound to
    ``parameter_name`` (and ``field_name``).

    Cached so repeated ``field_list_filter()`` calls for the same
    ``(class, field)`` pair across requests reuse one dynamic subclass
    instead of creating a new one every time.
    """
    return type(
        f"{select_filter_class.__name__}[{parameter_name}]",
        (select_filter_class,),
        {"parameter_name": parameter_name, "field_name": field_name},
    )


def field_list_filter(
    select_filter_class: type[BaseSelectFilter],
    parameter_name: str | None = None,
) -> Any:
    """Adapt ``select_filter_class`` for ``list_filter``'s ``(field_name,
    filter_class)`` tuple shorthand — Django's built-in way to reuse one
    filter class across several fields without a dedicated ``parameter_name``
    subclass per field::

        list_filter = [
            ("author", field_list_filter(ForeignKeyFilter)),
            ("genre", field_list_filter(ChoiceFilter)),
        ]

    Plain classes (``AuthorFilter`` set with its own ``parameter_name = "author"``)
    still work as before and can be mixed freely with this form.

    The URL's parameter is the field's path (``?author__country=3``), unless
    ``parameter_name`` names it (``field_list_filter(ForeignKeyFilter,
    parameter_name="country")``: ``?country=3``, filtering by the field).

    This can't return ``select_filter_class`` itself: for a tuple entry,
    Django calls the second element as
    ``filter_class(field, request, params, model, model_admin, field_path=...)``
    — a different signature from :class:`BaseSelectFilter`'s
    ``(request, params, model, model_admin)`` (Django's own
    ``FieldListFilter`` protocol, which ``BaseSelectFilter`` doesn't
    implement). This wraps that call instead, deriving ``parameter_name``
    from ``field_path`` and constructing ``select_filter_class`` normally —
    it works because Django only actually requires the returned object to
    support ``choices()``, ``has_output()`` and the other
    :class:`~django.contrib.admin.filters.SimpleListFilter` methods that
    :class:`BaseSelectFilter` already provides, not a real ``FieldListFilter``
    subclass.

    Only supports ``async_call = False``. ``Select2FilterOptionsView`` finds
    a matching *async* filter by looking for a ``list_filter`` entry whose
    own ``parameter_name`` equals the requested one — but this factory's
    ``parameter_name`` isn't fixed; it's only known once Django calls it for
    a specific field, so there's no single value to match against ahead of
    time. Use a dedicated subclass for an ``async_call`` filter instead.
    """
    if select_filter_class.async_call:
        raise TypeError(
            f"field_list_filter() doesn't support async_call filters "
            f"({select_filter_class.__name__}.async_call is True); use a "
            "dedicated subclass instead."
        )

    def factory(
        field: Any,
        request: HttpRequest,
        params: dict[str, Any],
        model: type[models.Model],
        model_admin: ModelAdmin[Any],
        field_path: str | None = None,
    ) -> BaseSelectFilter:
        path = field_path if field_path is not None else field.name
        bound_class = _bind_parameter_name(
            select_filter_class,  # type: ignore[arg-type]
            parameter_name or path,
            path if parameter_name else None,
        )
        return bound_class(request, params, model, model_admin)

    return factory
