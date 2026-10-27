"""field_name: the URL's parameter isn't the lookup it filters by."""

from django.contrib import admin
from django.test import RequestFactory

from django_admin_select_filter.filters import (
    ChoiceFilter,
    ForeignKeyFilter,
    field_list_filter,
)
from tests.cases import SelectFilterCase
from tests.testapp.models import Author, Book, Country


class WriterFilter(ForeignKeyFilter):
    parameter_name = "writer"
    field_name = "author"


class CountryFilter(ForeignKeyFilter):
    parameter_name = "country"
    field_name = "author__country"


class KindFilter(ChoiceFilter):
    parameter_name = "kind"
    field_name = "genre"


class TestFieldName(SelectFilterCase):
    """``?writer=3`` filtering by ``author``."""

    def _filter(self, filter_class, params=None):
        request = RequestFactory().get("/admin/tests/book/")
        return filter_class(request, params or {}, Book, admin.site._registry[Book])

    def test_field_lookup_is_field_name_else_parameter_name(self):
        assert self._build(parameter_name="writer").field_lookup == "writer"
        assert (
            self._build(parameter_name="writer", field_name="author").field_lookup
            == "author"
        )

    def test_filters_by_field_name_from_the_parameter(self):
        rowling = Author.objects.create(name="Rowling")
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="HP", author=rowling)
        Book.objects.create(title="LOTR", author=tolkien)

        filter_instance = self._filter(WriterFilter, {"writer": [str(rowling.pk)]})

        assert filter_instance.parameter_name == "writer"
        assert filter_instance.model is Author
        assert filter_instance.title == "authors"
        assert list(filter_instance.get_options()) == [rowling, tolkien]
        result = filter_instance.queryset(None, Book.objects.all())
        assert list(result.values_list("title", flat=True)) == ["HP"]

    def test_infers_the_model_across_a_nested_field_name(self):
        uk = Country.objects.create(name="UK")
        Country.objects.create(name="Unused")
        rowling = Author.objects.create(name="Rowling", country=uk)
        Book.objects.create(title="HP", author=rowling)
        Book.objects.create(title="Orphan", author=None)

        filter_instance = self._filter(CountryFilter, {"country": [str(uk.pk)]})

        assert filter_instance.model is Country
        assert list(filter_instance.get_options()) == [uk]
        result = filter_instance.queryset(None, Book.objects.all())
        assert list(result.values_list("title", flat=True)) == ["HP"]

    def test_null_option_by_field_name(self):
        Book.objects.create(title="Orphan", author=None)
        Book.objects.create(title="HP", author=Author.objects.create(name="Rowling"))

        filter_instance = self._filter(WriterFilter, {"writer": ["__null__"]})

        assert filter_instance.nullable is True
        assert filter_instance._has_null_option()
        result = filter_instance.queryset(None, Book.objects.all())
        assert list(result.values_list("title", flat=True)) == ["Orphan"]

    def test_multiple_values_by_field_name(self):
        rowling = Author.objects.create(name="Rowling")
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="HP", author=rowling)
        Book.objects.create(title="LOTR", author=tolkien)
        Book.objects.create(title="Orphan", author=None)

        class MultipleWriterFilter(WriterFilter):
            multiple = True

        filter_instance = self._filter(
            MultipleWriterFilter, {"writer": [f"{rowling.pk},__null__"]}
        )
        result = filter_instance.queryset(None, Book.objects.all())
        assert set(result.values_list("title", flat=True)) == {"HP", "Orphan"}

    def test_choice_filter_by_field_name(self):
        Book.objects.create(title="Dune", genre="fiction")
        Book.objects.create(title="Odes", genre="poetry")

        filter_instance = self._filter(KindFilter, {"kind": ["poetry"]})

        assert filter_instance.title == "genre"
        assert [value for value, _ in filter_instance.options] == [
            "fiction",
            "nonfiction",
            "poetry",
        ]
        result = filter_instance.queryset(None, Book.objects.all())
        assert list(result.values_list("title", flat=True)) == ["Odes"]

    def test_async_facet_counts_by_field_name(self):
        Book.objects.create(title="A", genre="fiction")
        Book.objects.create(title="B", genre="fiction")

        filter_instance = self._build(
            parameter_name="kind",
            field_name="genre",
            model_admin=admin.site._registry[Book],
            request=RequestFactory().get("/admin/"),
        )
        assert filter_instance._get_option_facet_counts() == {"fiction": 2}


class TestFieldListFilterParameterName(SelectFilterCase):
    """``field_list_filter(…, parameter_name=…)``: its own URL parameter."""

    def test_names_the_parameter_and_filters_by_the_field_path(self):
        uk = Country.objects.create(name="UK")
        rowling = Author.objects.create(name="Rowling", country=uk)
        Book.objects.create(title="HP", author=rowling)
        Book.objects.create(title="Orphan", author=None)
        field = Author._meta.get_field("country")
        request = RequestFactory().get("/admin/")

        factory = field_list_filter(ForeignKeyFilter, parameter_name="country")
        filter_instance = factory(
            field,
            request,
            {"country": [str(uk.pk)]},
            Book,
            admin.site._registry[Book],
            field_path="author__country",
        )

        assert filter_instance.parameter_name == "country"
        assert filter_instance.field_name == "author__country"
        assert filter_instance.model is Country
        result = filter_instance.queryset(request, Book.objects.all())
        assert list(result.values_list("title", flat=True)) == ["HP"]
