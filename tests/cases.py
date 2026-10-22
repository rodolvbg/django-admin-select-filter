"""What the tests of the filters share."""

from unittest.mock import patch

import django
from django.contrib.admin.filters import SimpleListFilter
from django.test import TestCase
from unittest_parametrize import ParametrizedTestCase

from django_admin_select_filter.filters import (
    BaseSelectFilter,
)


def _changelist_params(params):
    """Adapt a ``{name: [value, ...]}`` params dict — the shape every
    filter construction in this file uses — to whatever shape Django's
    own ``ChangeList`` actually passes to a list filter's constructor
    for the installed Django version: a list per key
    (``request.GET.lists()``) from Django 5.0 on, a single scalar value
    per key (``request.GET.items()``) before that.
    """
    if not params:
        return {}
    if django.VERSION >= (5, 0):
        return {
            key: value if isinstance(value, list) else [value]
            for key, value in params.items()
        }
    return {
        key: value[-1] if isinstance(value, list) else value
        for key, value in params.items()
    }


def _adapt_filter_params_to_django_version():
    """Every filter construction in this file passes ``params`` shaped
    for Django 5.0+ (a list of raw values per key). Real Django < 5.0
    builds a single scalar per key instead — the filter classes under
    test never build this dict themselves, they only read
    ``self.used_parameters``, which ``SimpleListFilter.__init__``
    populates from whatever shape ``params`` arrives in. Patching that
    one shared choke point (rather than every one of this file's ~20
    call sites) adapts every filter construction transparently, so
    tests don't silently return empty querysets on Django < 5.0 instead
    of exercising the real behavior. Returns the started patcher.
    """
    original_init = SimpleListFilter.__init__

    def patched_init(self, request, params, model, model_admin):
        original_init(self, request, _changelist_params(params), model, model_admin)

    return patch.object(SimpleListFilter, "__init__", patched_init)


class _FakeChangeList:
    add_facets = False

    def get_query_string(self, new_params=None, remove=None):
        return "?author=1"


class _FakeModelAdmin:
    def __init__(self, queryset):
        self.queryset = queryset
        self.calls = 0

    def get_queryset(self, request):
        self.calls += 1
        return self.queryset


class SelectFilterCase(ParametrizedTestCase, TestCase):
    """A BaseSelectFilter built with only the attributes a test needs."""

    def setUp(self):
        patcher = _adapt_filter_params_to_django_version()
        patcher.start()
        self.addCleanup(patcher.stop)

    def _build(self, **attrs):
        filter_instance = BaseSelectFilter.__new__(BaseSelectFilter)
        defaults = {
            "all_value": "__all__",
            "null_value": "__null__",
            "filter_only_used_values": True,
            "async_call": False,
            "nullable": None,
            "parameter_name": None,
            "used_parameters": {},
            **attrs,
        }
        for name, value in defaults.items():
            setattr(filter_instance, name, value)
        return filter_instance
