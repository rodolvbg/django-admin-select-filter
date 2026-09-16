from django.contrib import admin

from django_admin_select_filter.filters import (
    ChoiceFilter,
    ForeignKeyFilter,
    field_list_filter,
)
from tests.testapp.models import Author, Book, Country


class AuthorFilter(ForeignKeyFilter):
    model = Author
    parameter_name = "author"
    ordering = ["name"]


class AllNullableAuthorFilter(AuthorFilter):
    filter_only_used_values = False


class FixedTitleAuthorFilter(AuthorFilter):
    title = "Fixed title"


class ExplicitNullableAuthorFilter(AuthorFilter):
    nullable = False


class AsyncAuthorFilter(AuthorFilter):
    async_call = True


class MultipleAuthorFilter(AuthorFilter):
    multiple = True


class MultipleAsyncAuthorFilter(AuthorFilter):
    multiple = True
    async_call = True


class OnlyNameAuthorFilter(ForeignKeyFilter):
    model = Author
    parameter_name = "author"
    only = ["name"]


class MissingFieldFilter(ForeignKeyFilter):
    model = Author
    parameter_name = "not_a_real_field"
    filter_only_used_values = False


class GenreFilter(ChoiceFilter):
    parameter_name = "genre"


class NonSearchableGenreFilter(GenreFilter):
    searchable = False


class AsyncGenreFilter(GenreFilter):
    async_call = True


class MultipleGenreFilter(GenreFilter):
    multiple = True
    filter_only_used_values = False


class MultipleAsyncGenreFilter(MultipleGenreFilter):
    async_call = True


class ExplicitOptionsGenreFilter(ChoiceFilter):
    parameter_name = "genre"
    options = [("fiction", "Fiction"), ("poetry", "Poetry")]


class AllGenresFilter(GenreFilter):
    filter_only_used_values = False


class FixedTitleGenreFilter(GenreFilter):
    title = "Fixed title"


class ExplicitOptionsMissingFieldFilter(ChoiceFilter):
    parameter_name = "not_a_real_field"
    options = [("a", "A")]
    filter_only_used_values = False


class AuthorStatusFilter(ChoiceFilter):
    parameter_name = "author__status"
    filter_only_used_values = False


class UnknownChainFilter(ChoiceFilter):
    parameter_name = "bogus__status"
    options = [("a", "A")]
    filter_only_used_values = False


class NonRelationChainFilter(ChoiceFilter):
    parameter_name = "title__status"
    options = [("a", "A")]
    filter_only_used_values = False


class AsyncCountryNameFilter(ChoiceFilter):
    parameter_name = "name"
    options = [("Chile", "Chile"), ("Peru", "Peru")]
    async_call = True
    filter_only_used_values = False


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin[Author]):
    search_fields = ["name"]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin[Book]):
    list_filter = [
        MissingFieldFilter,
        AuthorFilter,
        AsyncAuthorFilter,
        GenreFilter,
        AsyncGenreFilter,
        # Tuple form: reuses ForeignKeyFilter directly (no dedicated
        # subclass) via field_list_filter(), on a nested lookup so the
        # target model (Country) is inferred automatically too.
        ("author__country", field_list_filter(ForeignKeyFilter)),
    ]


# A second, uncluttered admin site for browser (Playwright) tests: BookAdmin
# above stacks edge-case filters for coverage purposes, which makes DOM
# selectors ambiguous for an end-to-end smoke test.
e2e_admin_site = admin.AdminSite(name="e2e_admin")


@admin.register(Author, site=e2e_admin_site)
class E2EAuthorAdmin(admin.ModelAdmin[Author]):
    search_fields = ["name"]


@admin.register(Book, site=e2e_admin_site)
class E2EBookAdmin(admin.ModelAdmin[Book]):
    list_filter = [AuthorFilter]


# Registered only on this custom site (never on the default django.contrib.admin
# site), to prove the async options view finds a model regardless of which
# AdminSite it's registered on.
@admin.register(Country, site=e2e_admin_site)
class E2ECountryAdmin(admin.ModelAdmin[Country]):
    list_filter = [AsyncCountryNameFilter]
