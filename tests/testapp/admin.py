from django.contrib import admin

from django_admin_select_filter.filters import ForeignKeyFilter
from tests.testapp.models import Author, Book


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


class OnlyNameAuthorFilter(ForeignKeyFilter):
    model = Author
    parameter_name = "author"
    only = ["name"]


class MissingFieldFilter(ForeignKeyFilter):
    model = Author
    parameter_name = "not_a_real_field"
    filter_only_used_values = False


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_filter = [MissingFieldFilter, AuthorFilter]
