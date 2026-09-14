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

The endpoint only serves filters with `async_call = True` and requires the
requesting user to have view permission on the target model (checked via
`ModelAdmin.has_view_permission`) — anonymous or unprivileged requests get a
403, and a `parameter_name` matching a non-async filter gets a 404.

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

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync
uv run playwright install --with-deps chromium
npm install
uv run pytest
uv run pre-commit install
```

`uv sync`/`uv run` install the `dev` and `test` dependency groups by default
(`[tool.uv] default-groups` in `pyproject.toml`) — no `--extra` flags needed.

Without uv:

```bash
pip install -e ".[test,dev]"
playwright install --with-deps chromium
npm install
pytest
pre-commit install
```

`tests/e2e/` drives a real Django admin page in a headless browser
(pytest-playwright) to check the Select2 widget actually renders and works —
both the synchronous dropdown and the asynchronous one, which exercises the
JS → `fetch` → view → DB round trip for real. It needs a browser installed
once via `playwright install`.

`pre-commit` runs ruff, mypy, django-upgrade, djade (template linting),
pyproject-fmt, biome and vitest (for the bundled JS/CSS). The `mypy` hook
runs against the project's own environment rather than an isolated one,
since `django-stubs` needs the package importable to resolve model/queryset
types — with uv, `uv run pre-commit run --all-files` picks up `.venv/bin`
automatically; without it, activate the venv first (or prefix commands with
its `bin/`).

### Coverage

`pytest` always runs with coverage on (`--cov`, see `[tool.pytest]` /
`[tool.coverage]` in `pyproject.toml`) and prints a terminal report. For the
bundled JS:

```bash
npm run coverage:js
```
