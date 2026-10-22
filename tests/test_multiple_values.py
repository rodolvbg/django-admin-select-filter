"""MultipleValuesMixin: several values at once."""

from django.contrib import admin
from django.test import RequestFactory

from tests.cases import SelectFilterCase, _FakeChangeList
from tests.testapp.models import Author, Book


class TestMultipleValuesMixin(SelectFilterCase):
    """MultipleValuesMixin: several values at once."""

    def test__build_async_options_multiple_skips_the_all_option(self):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        Book.objects.create(title="Orphan", author=None)
        model_admin = admin.site._registry[Book]
        items = [(str(author.pk), "Rowling")]

        filter_instance = self._build(
            nullable=False,
            parameter_name="author",
            multiple=True,
            model_admin=model_admin,
            request=RequestFactory().get("/admin/"),
        )
        options = filter_instance._build_async_options(
            RequestFactory().get("/api/"), items
        )
        assert options == items

    def test_selected_values_multiple_mode_splits_on_the_separator(self):
        filter_instance = self._build(
            parameter_name="x", used_parameters={"x": "a,b"}, multiple=True
        )
        assert filter_instance.selected_values() == ["a", "b"]

    def test_selected_values_multiple_mode_drops_empty_segments(self):
        filter_instance = self._build(
            parameter_name="x", used_parameters={"x": "a,,b,"}, multiple=True
        )
        assert filter_instance.selected_values() == ["a", "b"]

    def test_queryset_multiple_values_filter_with_in(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name="author",
            used_parameters={"author": f"{author.pk},{tolkien.pk}"},
            multiple=True,
        )
        result = filter_instance.queryset(request, all_books)
        assert set(result.values_list("title", flat=True)) == {"HP", "LOTR"}

    def test_queryset_multiple_values_combine_in_with_the_null_lookup(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name="author",
            used_parameters={"author": f"{author.pk},__null__"},
            multiple=True,
        )
        result = filter_instance.queryset(request, all_books)
        assert set(result.values_list("title", flat=True)) == {"HP", "Orphan"}

    def test_queryset_multiple_with_only_the_null_value_selected(self):
        Book.objects.create(title="Orphan", author=None)
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="HP", author=author)
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="LOTR", author=tolkien)
        request = RequestFactory().get("/admin/tests/book/")
        all_books = Book.objects.all()

        filter_instance = self._build(
            parameter_name="author",
            used_parameters={"author": "__null__"},
            multiple=True,
        )
        result = filter_instance.queryset(request, all_books)
        assert list(result.values_list("title", flat=True)) == ["Orphan"]

    def test_media_multiple_adds_multiple_navigation_js(self):
        filter_instance = self._build(multiple=True)
        assert "admin_select_filter/js/multiple_navigation.js" in str(
            filter_instance.media["js"]
        )

    def test_choices_multiple_selection_marks_every_selected_key(self):
        filter_instance = self._build(
            parameter_name="x",
            used_parameters={"x": "a,b"},
            multiple=True,
            lookup_choices=[("a", "Label A"), ("b", "Label B"), ("c", "Label C")],
        )
        choices = list(filter_instance.choices(_FakeChangeList()))
        assert [choice["selected"] for choice in choices] == [False, True, True, False]
