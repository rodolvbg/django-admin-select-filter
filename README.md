# django-admin-select-filter

Select2-powered admin list filters for Django.

## Install

```bash
pip install django-admin-select-filter
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "django_admin_select_filter",
]
```

Wire the options endpoint (only needed for filters using `async_call = True`):

```python
# urls.py
urlpatterns = [
    ...
    path("admin/select-filter/", include("django_admin_select_filter.urls")),
]
```

The filter template loads jQuery/Select2 from Django admin's bundled vendor
assets on demand, so no extra JS dependency is required. Make sure
`django.contrib.staticfiles` is installed and configured.

## Usage

```python
from django.contrib import admin
from django_admin_select_filter.filters import ForeignKeyFilter

from myapp.models import Author, Book


class AuthorFilter(ForeignKeyFilter):
    model = Author
    parameter_name = "author"
    ordering = ["name"]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_filter = [AuthorFilter]
```

## Development

```bash
pip install -e ".[test,dev]"
pytest
```
