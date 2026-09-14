# Changelog

## Unreleased

- Initial project structure: `AdminSelectFilterMixin`, `ForeignKeyFilter`, async
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
