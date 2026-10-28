"""field_list_filter(): a filter class for list_filter's tuples."""

import pytest
from django.contrib import admin
from django.contrib.admin.filters import FieldListFilter
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from unittest_parametrize import ParametrizedTestCase

from django_admin_select_filter.filters import (
    ChoiceFilter,
    ForeignKeyFilter,
    field_list_filter,
)
from tests.cases import _adapt_filter_params_to_django_version
from tests.testapp.models import Author, Book, Country


class TestFieldListFilter(ParametrizedTestCase, TestCase):
    """The field_list_filter factory for the (field, filter) tuple form."""

    def setUp(self):
        patcher = _adapt_filter_params_to_django_version()
        patcher.start()
        self.addCleanup(patcher.stop)

    """Tests for the ``list_filter = [("field", field_list_filter(...))]`` form."""

    def _resolved_field(self, model, field_path):
        for part in field_path.split("__")[:-1]:
            model = model._meta.get_field(part).related_model
        return model._meta.get_field(field_path.rsplit("__", 1)[-1])

    def test_produces_bound_instance_inferring_parameter_name_from_field_path(
        self,
    ):
        author = Author.objects.create(name="Rowling")
        country = Country.objects.create(name="UK")
        author.country = country
        author.save()
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = self._resolved_field(Book, "author__country")
        factory = field_list_filter(ForeignKeyFilter)
        filter_instance = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )

        assert filter_instance.parameter_name == "author__country"

    def test_produces_bound_instance_inferring_model_from_nested_lookup(
        self,
    ):
        author = Author.objects.create(name="Rowling")
        country = Country.objects.create(name="UK")
        author.country = country
        author.save()
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = self._resolved_field(Book, "author__country")
        factory = field_list_filter(ForeignKeyFilter)
        filter_instance = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )

        assert filter_instance.model is Country

    def test_produces_bound_instance_behaving_like_a_foreign_key_filter(
        self,
    ):
        author = Author.objects.create(name="Rowling")
        country = Country.objects.create(name="UK")
        author.country = country
        author.save()
        Book.objects.create(title="HP", author=author)
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = self._resolved_field(Book, "author__country")
        factory = field_list_filter(ForeignKeyFilter)
        filter_instance = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )

        assert list(filter_instance.get_options()) == [country]

    def test_falls_back_to_field_name_without_field_path(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = Book._meta.get_field("genre")

        factory = field_list_filter(ChoiceFilter)
        filter_instance = factory(field, request, {}, Book, model_admin)

        assert filter_instance.parameter_name == "genre"

    def test_reuses_the_same_bound_class_across_calls(self):
        request = RequestFactory().get("/admin/")
        model_admin = admin.site._registry[Book]
        field = self._resolved_field(Book, "author__country")
        factory = field_list_filter(ForeignKeyFilter)

        first = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )
        second = factory(
            field, request, {}, Book, model_admin, field_path="author__country"
        )

        assert type(first) is type(second)

    def test_is_a_field_list_filter_for_djangos_checks(self):
        """admin.E115: a tuple's filter must be a FieldListFilter subclass."""
        factory = field_list_filter(ForeignKeyFilter)

        assert issubclass(factory, FieldListFilter)
        assert factory.__name__ == "ForeignKeyFilterFieldListFilter"
        assert factory is field_list_filter(ForeignKeyFilter)
        assert factory is not field_list_filter(ForeignKeyFilter, "country")
        assert admin.site._registry[Book].check() == []

    def test_rejects_an_async_call_filter(self):
        class AsyncFK(ForeignKeyFilter):
            async_call = True

        with pytest.raises(TypeError, match="doesn't support async_call"):
            field_list_filter(AsyncFK)

    def test_changelist_renders_the_tuple_form_filter(self):
        """End-to-end: BookAdmin.list_filter includes
        ``("author__country", field_list_filter(ForeignKeyFilter))``; make
        sure Django's own ChangeList machinery accepts it, not just a direct
        call to the factory.
        """
        author = Author.objects.create(name="Rowling")
        country = Country.objects.create(name="UK")
        author.country = country
        author.save()
        Book.objects.create(title="HP", author=author)

        request = RequestFactory().get("/admin/tests/book/")
        request.user = User.objects.create_superuser(
            "field_list_filter_admin", "flf@example.com", "password"
        )
        model_admin = admin.site._registry[Book]
        filter_specs, *_ = model_admin.get_changelist_instance(request).get_filters(
            request
        )
        matching = [
            spec
            for spec in filter_specs
            if isinstance(spec, ForeignKeyFilter)
            and spec.parameter_name == "author__country"
        ]

        assert len(matching) == 1
        assert list(matching[0].get_options()) == [country]
