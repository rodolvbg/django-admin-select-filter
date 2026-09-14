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

from myapp.models import Book


class AuthorFilter(ForeignKeyFilter):
    parameter_name = "author"
    ordering = ["name"]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_filter = [AuthorFilter]
```

`model` is only needed when it can't be inferred. By default it's resolved by
walking `parameter_name` across `Book`'s relations, following a nested lookup
(e.g. `parameter_name = "author__country"`) segment by segment — forward or
reverse — and taking the last segment's related model. Set `model` explicitly
if the lookup isn't a real relation chain, or to point somewhere else.

For a field that isn't a relation — a `choices`-backed `CharField`/`IntegerField`,
a `BooleanField`, or anything else with discrete values — use `ChoiceFilter`
instead. It reads its options from the field's `choices` by default, or from an
explicit `options` list:

```python
from django_admin_select_filter.filters import ChoiceFilter


class GenreFilter(ChoiceFilter):
    parameter_name = "genre"  # reads Book.genre.choices


class StatusFilter(ChoiceFilter):
    parameter_name = "status"
    options = [("draft", "Draft"), ("published", "Published")]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_filter = [AuthorFilter, GenreFilter]
```

Both filters share the same options: `filter_only_used_values`, `async_call`,
`autocomplete`, `nullable` and `title`. Both also support a nested lookup for
`parameter_name` (e.g. `"author__status"`), resolving the field — and, for
`ForeignKeyFilter`, the `model` — by walking each `__`-separated relation in
turn, forward or reverse.

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
