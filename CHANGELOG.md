# Changelog

## Unreleased

- Initial project structure: `AdminSelectFilterMixin`, `ForeignKeyFilter`, async
  options view/URL, Select2 filter template, and test scaffolding.
- Extracted shared filter logic into `BaseSelectFilter` and added `ChoiceFilter`,
  a general-purpose Select2 filter for scalar fields (e.g. `ChoiceField`) or
  explicit `(value, label)` options, not tied to a related model.
