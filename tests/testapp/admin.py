from django.contrib import admin

from django_admin_select_filter.filters import ForeignKeyFilter
from tests.testapp.models import Author, Book


class AuthorFilter(ForeignKeyFilter):
    model = Author
    parameter_name = "author"
    ordering = ["name"]


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    pass


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_filter = [AuthorFilter]
