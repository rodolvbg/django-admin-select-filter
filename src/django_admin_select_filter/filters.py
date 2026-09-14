from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from django.contrib.admin import ModelAdmin
from django.contrib.admin.filters import SimpleListFilter
from django.db import models
from django.http import HttpRequest
from django.utils.functional import cached_property
from django.utils.translation import gettext

from django_admin_select_filter.mixins import AdminSelectFilterMixin


class ForeignKeyFilter(AdminSelectFilterMixin, SimpleListFilter):
    """Filter an admin changelist by selectable related-model instances.

    Subclasses configure the filter through these class attributes:

    ``model``
        Related model whose instances become the available options. Required.
    ``parameter_name``
        Lookup applied to the changelist queryset, such as ``"group"`` or
        ``"groups"``. Required.
    ``ordering``
        Field names used to order the related instances.
    ``only``
        Related-model fields loaded by the options queryset. Include every
        field needed by the model's string representation.
    ``filter_only_used_values``
        When true, only expose relations already present in the current
        ModelAdmin queryset. It defaults to true.
    ``async_call``
        When true, defer loading options until Select2 requests them through
        the API. It defaults to false.
    ``nullable``
        Controls whether the ``-`` option is available. When left as ``None``,
        the value is inferred from the configured model field.
    ``title``
        Label shown by Django above the filter. By default it uses the related
        model admin's plural verbose name.

    ``all_value`` and ``null_value`` are reserved values used by the async API
    for the translated “All” option and the null option, respectively. They can
    be overridden if those values conflict with valid primary keys.
    """

    model: ClassVar[type[models.Model] | None] = None
    ordering: ClassVar[list[str]] = []
    only: ClassVar[list[str]] = []
    filter_only_used_values: ClassVar[bool] = True
    async_call: ClassVar[bool] = False
    nullable: bool | None = None
    all_value: ClassVar[str] = "__all__"
    null_value: ClassVar[str] = "__null__"
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
        if self.model is None:
            raise TypeError(f"{type(self).__name__}.model must be configured")

        if self.title is None:
            registered_admin = model_admin.admin_site._registry.get(self.model)
            title_model = (
                registered_admin.model if registered_admin is not None else self.model
            )
            self.title = title_model._meta.verbose_name_plural
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

        super().__init__(request, params, admin_model, model_admin)

    @cached_property
    def model_admin_queryset(self) -> models.QuerySet[Any]:
        """Return and cache the source ModelAdmin queryset when first needed."""
        return self.model_admin.get_queryset(self.request)

    def _is_nullable(self, admin_model: type[models.Model]) -> bool:
        """Determine whether the configured relation accepts null values."""
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

    def get_async_options(
        self,
        request: HttpRequest,
        q: str,
    ) -> list[tuple[str, str]]:
        """Return Select2 options for an API request and its search term.

        ``self.request`` is the admin changelist request used to construct the
        filter. ``request`` is the separate API-view request that asks for the
        asynchronous options, and ``q`` is the search term sent by that view.
        :param request: The API-view request asking for asynchronous options.
        :param q: The search term sent by the API-view request.
        :return: A list of tuples representing the Select2 options.
        """
        options = [(self.all_value, gettext("All"))]
        options.extend(
            (str(instance.pk), str(instance))
            for instance in self.get_options(request=request, q=q)
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

    def _get_option_facet_counts(self) -> dict[str, int]:
        """Count related options for either filter presentation.

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

    def lookups(
        self,
        request: HttpRequest,
        model_admin: ModelAdmin[Any],
    ) -> list[tuple[str, str]]:
        """Return choices rendered initially by Django's list-filter template."""
        assert self.model is not None
        if self.async_call:
            selected_value = self.value()
            selected = (
                self.model._default_manager.filter(pk=selected_value).first()
                if selected_value and selected_value != self.null_value
                else None
            )
            options = [(str(selected.pk), str(selected))] if selected else []
        else:
            options = [
                (str(instance.pk), str(instance)) for instance in self.get_options()
            ]
        if self.has_null_option:
            options.append((self.null_value, "-"))
        return options

    def has_output(self) -> bool:
        """Keep asynchronous filters visible before their options are loaded."""
        return self.async_call or super().has_output()

    def queryset(
        self,
        request: HttpRequest,
        queryset: models.QuerySet[Any],
    ) -> models.QuerySet[Any]:
        """Apply the selected related or null value to the changelist queryset."""
        value = self.value()
        if value is None or self.parameter_name is None:
            return queryset
        if value == self.null_value:
            return queryset.filter(**{f"{self.parameter_name}__isnull": True})
        return queryset.filter(**{self.parameter_name: value})

    def choices(self, changelist: Any) -> Iterator[dict[str, Any]]:  # type: ignore[override]
        """Yield Django choices with the raw lookup key required by Select2."""
        for index, choice in enumerate(super().choices(changelist)):
            key = "" if index == 0 else str(self.lookup_choices[index - 1][0])
            yield {**choice, "key": key}
