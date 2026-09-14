# Changelog

## Unreleased

- Added `BaseSelectFilter.media`: a property returning a real
  `django.forms.Media` instance, computed from the filter's own
  configuration — mirrors `ModelAdmin.media`'s own pattern of a `@property`
  building `Media` from instance state. `base.html` now renders
  `{{ spec.media.css }}`/`{{ spec.media.js }}` instead of hardcoding one
  `{% if %}` block per optional JS module. Since `Media.render_js()` can't
  add a `type="module"` attribute before Django 5.2, each JS entry is a
  `mark_safe()`-wrapped `<script type="module">` string — `Media` has always
  rendered such entries via their own `__html__()` instead of building the
  tag itself, so this works back to Django 4.2.
- Split the bundled JS into `core.js` (jQuery/Select2 bootstrap and default
  navigation) plus one module per optional capability — `async_options.js`,
  `multiple_navigation.js`, `non_searchable.js` — each registering itself
  into `core.js` via a small plugin interface (`appliesTo`/`extendOptions`/
  `bindEvents`). `base.html` only emits the `<script type="module">` tag for
  a capability module when the rendered filter actually needs it (e.g.
  `async_call`, `multiple`, `searchable = False`), instead of always shipping
  every code path. `core.js` now defers its own initialization until
  `DOMContentLoaded` so every capability module on the page — regardless of
  which filter requested it or its tag's position — has registered itself
  first.
