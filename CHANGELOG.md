# Changelog

## Unreleased

- Initial project structure: `BaseSelectFilter`,`ForeignKeyFilter`, async
  options view/URL, Select2 filter template, and test scaffolding.
- Extracted shared filter logic into `BaseSelectFilter` and added `ChoiceFilter`,
  a general-purpose Select2 filter for scalar fields (e.g. `ChoiceField`) or
  explicit `(value, label)` options, not tied to a related model.
- `ForeignKeyFilter.model` is now optional: when unset, it's inferred by
  walking `parameter_name` across the admin model's relations, including a
  nested lookup like `"publisher__country"`.
- Extracted that relation-walking into `BaseSelectFilter._resolve_field`, so
  `ChoiceFilter` also supports a nested `parameter_name` (e.g.
  `"author__status"`) when deriving options from field `choices`.
- Moved the Select2 filter template out of the generic `admin/filters/` path
  into `admin_select_filter/filters/`, namespaced under the app's own label
  (matching the existing static files and URL namespace) instead of a path
  other packages could collide with. Split it into a
  `base.html` with the shared markup and blocks, and a
  `foreign_key_filter.html`/`choice_filter.html` pair that each extend it —
  `ForeignKeyFilter` and `ChoiceFilter` now set their own `template`.
- Added `BaseSelectFilter.multiple`: both filters can now select several
  values at once, filtering with an `__in` lookup (combined with the null
  lookup when the null option is also selected). Selected values are joined
  in the query string via `multiple_separator`. The Select2 widget switches
  to its native multi-select mode and the JS waits for the dropdown to close
  before navigating, instead of navigating on every single selection.
- `BaseSelectFilter`, `ForeignKeyFilter` and `ChoiceFilter` are now importable
  directly from `django_admin_select_filter` (e.g.
  `from django_admin_select_filter import ForeignKeyFilter`), not just from
  `django_admin_select_filter.filters`.
- Fixed `Select2FilterOptionsView` returning 404 when the target model was
  registered on a project's own `AdminSite` instead of the default
  `django.contrib.admin.site`. It now checks every registered `AdminSite`.
- Added `BaseSelectFilter.searchable`: set to `False` to hide Select2's
  search input and get a plain dropdown, for a short static option list.
- Fixed dark-mode styling for `multiple = True`: the CSS only targeted
  Select2's single-selection markup, leaving the multi-select chips unstyled.
- Replaced `django_admin_select_filter.urls`'s plain `urlpatterns` list with
  `django_admin_select_filter_path()`, a function projects drop straight
  into their own `urlpatterns` — no `include()` needed. It still namespaces
  the route as `admin_select_filter:options` internally via `include()`, and
  accepts `route` (defaults to `"django_admin_select_filter/options/"`),
  `view`, `name` and `as_view_kwargs` to customize it.
- Added `BaseSelectFilter.async_call_url`: the JS now reads the async
  endpoint from this per-filter attribute. Left unset (the default), it
  resolves via `reverse("admin_select_filter:options")` at request time, so
  it's always correct regardless of the admin page it's rendered on and
  wherever that urlconf is mounted (a bare relative path there would resolve
  against the *current page*, not that mount point, and silently hit the
  wrong URL). Set it explicitly on a filter to point it at a custom view — or
  to match a custom `name=` passed to `django_admin_select_filter_path()`,
  which filters otherwise have no way to discover.
- Added `Select2FilterOptionsView.use_registry`: enabled via
  `as_view_kwargs={"use_registry": True}`, it resolves the matching filter
  from a `{site: {app_label: {model_name: {parameter_name: filter}}}}` map
  built once and cached for the process's lifetime, instead of calling
  `get_list_filter()` on every registered `ModelAdmin` on every request.
- Added `field_list_filter()`, adapting `ForeignKeyFilter`/`ChoiceFilter` for
  `list_filter`'s `(field_name, filter_class)` tuple shorthand so the same
  class can be reused across fields without a dedicated subclass per field —
  `parameter_name` (and, for `ForeignKeyFilter`, `model`) is inferred from
  the field. Only supports `async_call = False`; it raises `TypeError`
  immediately for a filter with `async_call = True`.
