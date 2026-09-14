from __future__ import annotations

import functools
from collections.abc import Iterator
from typing import Any, ClassVar

from django.contrib.admin import ModelAdmin
from django.contrib.admin.filters import SimpleListFilter
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.http import HttpRequest
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext

# The default ``name`` django_admin_select_filter_path() registers its route
# under. Imported from there (rather than declared alongside it) so filters
# and urls.py share one source of truth without a circular import — urls.py
# already depends on views.py, which depends on this module.
ASYNC_CALL_URL_NAME = "options"


class BaseSelectFilter(SimpleListFilter):
    """Shared plumbing for the project's Select2-powered admin list filters.

    Handles everything that doesn't depend on where the options come from:
    null-value support, facet counts, queryset filtering by the raw lookup
    value, and the Select2 template's ``choices()`` rendering. Subclasses
    only need to supply the available options (see ``get_options``,
    ``get_async_options`` and ``lookups`` on :class:`ForeignKeyFilter` and
    :class:`ChoiceFilter` for the two supported shapes).

    ``parameter_name``
        Lookup applied to the changelist queryset, such as ``"group"`` or
        ``"groups"``. Required.
    ``filter_only_used_values``
        When true, only expose relations already present in the current
        ModelAdmin queryset. It defaults to true.
    ``async_call``
        When true, defer loading options until Select2 requests them through
        the API. It defaults to false.
    ``searchable``
        When false, hide Select2's search input and behave like a plain
        dropdown. Best for a short, static option list. It defaults to true.
    ``nullable``
        Controls whether the ``-`` option is available. When left as ``None``,
        the value is inferred from the configured model field.
    ``title``
        Label shown by Django above the filter. By default it uses the related
        model admin's plural verbose name.
    ``multiple``
        When true, the Select2 widget accepts several values at once and
        ``queryset()`` filters with an ``__in`` lookup. Selected values are
        stored in the query string joined by ``multiple_separator``, so
        configured values (primary keys, option values) must not contain it.
        It defaults to false.
    ``multiple_separator``
        Character joining multiple selected values in the query string. It
        defaults to ``","``.
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

    filter_only_used_values: ClassVar[bool] = True
    async_call: ClassVar[bool] = False
    searchable: ClassVar[bool] = True
    nullable: bool | None = None
    all_value: ClassVar[str] = "__all__"
    null_value: ClassVar[str] = "__null__"
    multiple: ClassVar[bool] = False
    multiple_separator: ClassVar[str] = ","
    async_call_url: str | None = None
    title: Any | None = None
    parameter_name: str | None = None

    def __init__(
        self,
        request: HttpRequest,
        params: dict[str, Any],
        admin_model: type[models.Model],
        model_admin: ModelAdmin[Any],
    ) -> None:
        """Configure the filter for an admin changelist request."""
        if self.nullable is None:
            self.nullable = self._is_nullable(admin_model)
        self.request = request
        self.model_admin = model_admin
        self.admin_app_label = admin_model._meta.app_label
        self.admin_model_name = admin_model._meta.model_name
        self.has_null_option = (
            not self.async_call or not self.filter_only_used_values
        ) and self._has_null_option()
        self.facets = self.request.GET.get("_facets") == "True"
        if self.async_call and self.async_call_url is None:
            self.async_call_url = reverse(f"admin_select_filter:{ASYNC_CALL_URL_NAME}")

        super().__init__(request, params, admin_model, model_admin)

    @cached_property
    def model_admin_queryset(self) -> models.QuerySet[Any]:
        """Return and cache the source ModelAdmin queryset when first needed."""
        return self.model_admin.get_queryset(self.request)

    def _is_nullable(self, admin_model: type[models.Model]) -> bool:
        """Determine whether the configured field accepts null values."""
        for field in admin_model._meta.get_fields():
            if self.parameter_name in (field.name, getattr(field, "attname", None)):
                return bool(getattr(field, "null", False))
        return False

    def _has_null_option(self) -> bool:
        """Return whether the filter should expose its null-value option."""
        if not self.nullable or self.parameter_name is None:
            return False
        if not self.filter_only_used_values:
            return True
        return self.model_admin_queryset.filter(
            **{f"{self.parameter_name}__isnull": True}
        ).exists()

    def _resolve_field(self, admin_model: type[models.Model]) -> Any | None:
        """Walk ``parameter_name`` across relations and return its final field.

        Handles a nested lookup, such as ``"publisher__country"``, by
        following each ``__``-separated segment's relation in turn — forward
        or reverse — except the last, whose field is returned as-is. Returns
        ``None`` when ``parameter_name`` is unset or any segment doesn't
        resolve to a real field.
        """
        if self.parameter_name is None:
            return None
        current_model: type[models.Model] = admin_model
        parts = self.parameter_name.split("__")
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

    def _get_option_facet_counts(self) -> dict[str, int]:
        """Count options for either filter presentation.

        Asynchronous filters use these counts in their API results. Synchronous
        filters may reuse the helper, although Django's standard list-filter
        rendering already calculates its own facet counts.
        """
        if self.parameter_name is None:
            return {}
        counts = (
            self.model_admin_queryset.order_by()
            .values(self.parameter_name)
            .annotate(count=models.Count("pk"))
        )
        return {
            self.null_value if value is None else str(value): count
            for value, count in counts.values_list(self.parameter_name, "count")
        }

    def _build_async_options(
        self,
        request: HttpRequest,
        items: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """Assemble the "All"/items/null options, applying facet counts if asked.

        The "All" option is skipped when ``multiple`` is enabled: clearing
        every selected value already means "no filter" for a multi-select.
        """
        options = (
            list(items) if self.multiple else [(self.all_value, gettext("All")), *items]
        )
        if self._has_null_option():
            options.append((self.null_value, "-"))
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

    def has_output(self) -> bool:
        """Keep asynchronous filters visible before their options are loaded."""
        return self.async_call or super().has_output()

    def selected_values(self) -> list[str]:
        """Return the selected raw values, splitting on ``multiple_separator``
        when ``multiple`` is enabled. Empty when nothing is selected."""
        value = self.value()
        if not value:
            return []
        if not self.multiple:
            return [value]
        return [item for item in value.split(self.multiple_separator) if item]

    def queryset(
        self,
        request: HttpRequest,
        queryset: models.QuerySet[Any],
    ) -> models.QuerySet[Any]:
        """Apply the selected value(s) or the null lookup to the changelist queryset."""
        if self.parameter_name is None:
            return queryset
        values = self.selected_values()
        if not values:
            return queryset
        if not self.multiple:
            value = values[0]
            if value == self.null_value:
                return queryset.filter(**{f"{self.parameter_name}__isnull": True})
            return queryset.filter(**{self.parameter_name: value})
        real_values = [value for value in values if value != self.null_value]
        condition = models.Q()
        if real_values:
            condition |= models.Q(**{f"{self.parameter_name}__in": real_values})
        if self.null_value in values:
            condition |= models.Q(**{f"{self.parameter_name}__isnull": True})
        return queryset.filter(condition)

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

    def _option_items(
        self,
        request: HttpRequest | None = None,
        q: str = "",
    ) -> list[tuple[str, str]]:
        """Return every available option as ``(key, label)`` string pairs."""
        raise NotImplementedError

    def _selected_option_items(self) -> list[tuple[str, str]]:
        """Return only the currently selected options, as ``(key, label)`` pairs."""
        raise NotImplementedError

    def get_async_options(
        self,
        request: HttpRequest,
        q: str,
    ) -> list[tuple[str, str]]:
        """Return Select2 options for an API request and its search term."""
        return self._build_async_options(
            request, self._option_items(request=request, q=q)
        )

    def lookups(
        self,
        request: HttpRequest,
        model_admin: ModelAdmin[Any],
    ) -> list[tuple[str, str]]:
        """Return choices rendered initially by Django's list-filter template."""
        options = (
            self._selected_option_items() if self.async_call else self._option_items()
        )
        if self.has_null_option:
            options.append((self.null_value, "-"))
        return options


class ForeignKeyFilter(BaseSelectFilter):
    """Filter an admin changelist by selectable related-model instances.

    Subclasses configure the filter through these class attributes:

    ``model``
        Related model whose instances become the available options. When left
        unset, it's inferred by walking ``parameter_name`` across the admin
        model's relations — including a nested lookup such as
        ``"publisher__country"`` — and taking the last relation's target
        model. Configure it explicitly when it can't be inferred (the lookup
        isn't a real relation chain) or to point elsewhere.
    ``ordering``
        Field names used to order the related instances.
    ``only``
        Related-model fields loaded by the options queryset. Include every
        field needed by the model's string representation.

    ``all_value`` and ``null_value`` are reserved values used by the async API
    for the translated “All” option and the null option, respectively. They can
    be overridden if those values conflict with valid primary keys.
    """

    template = "admin_select_filter/filters/foreign_key_filter.html"
    model: type[models.Model] | None = None
    ordering: ClassVar[list[str]] = []
    only: ClassVar[list[str]] = []

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
                f"{self.parameter_name!r} must resolve to a related model"
            )

        if self.title is None:
            registered_admin = model_admin.admin_site._registry.get(self.model)
            title_model = (
                registered_admin.model if registered_admin is not None else self.model
            )
            self.title = title_model._meta.verbose_name_plural
        super().__init__(request, params, admin_model, model_admin)

    def _resolve_model(
        self, admin_model: type[models.Model]
    ) -> type[models.Model] | None:
        """Return ``parameter_name``'s target model, following relations.

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
        if self.filter_only_used_values and self.parameter_name is not None:
            used_values = self.model_admin_queryset.values_list(
                self.parameter_name, flat=True
            )
            queryset = queryset.filter(pk__in=used_values)
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
    ) -> list[tuple[str, str]]:
        """Return every available option as ``(key, label)`` string pairs."""
        return [
            (str(instance.pk), str(instance))
            for instance in self.get_options(request=request, q=q)
        ]

    def _selected_option_items(self) -> list[tuple[str, str]]:
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
                    f"{self.parameter_name!r} must name a field with choices"
                )
            self.options = [(value, str(label)) for value, label in field_choices]
        if self.title is None:
            self.title = (
                field.verbose_name if field is not None else self.parameter_name
            )
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
        if self.filter_only_used_values and self.parameter_name is not None:
            used_values = set(
                self.model_admin_queryset.exclude(
                    **{f"{self.parameter_name}__isnull": True}
                ).values_list(self.parameter_name, flat=True)
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
    ) -> list[tuple[str, str]]:
        """Return every available option as ``(key, label)`` string pairs."""
        return [
            (str(value), label)
            for value, label in self.get_options(request=request, q=q)
        ]

    def _selected_option_items(self) -> list[tuple[str, str]]:
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
    select_filter_class: type[BaseSelectFilter], parameter_name: str
) -> type[BaseSelectFilter]:
    """Return (and cache) a ``select_filter_class`` subclass bound to ``parameter_name``.

    Cached so repeated ``field_list_filter()`` calls for the same
    ``(class, field)`` pair across requests reuse one dynamic subclass
    instead of creating a new one every time.
    """
    return type(
        f"{select_filter_class.__name__}[{parameter_name}]",
        (select_filter_class,),
        {"parameter_name": parameter_name},
    )


def field_list_filter(
    select_filter_class: type[BaseSelectFilter],
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
        parameter_name = field_path if field_path is not None else field.name
        bound_class = _bind_parameter_name(select_filter_class, parameter_name)  # type: ignore[arg-type]
        return bound_class(request, params, model, model_admin)

    return factory
