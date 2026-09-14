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
- `BaseSelectFilter.media` now also emits a `<script type="importmap">`
  mapping the bare specifier `"core"` to `core.js`'s `static()` URL, and
  `async_options.js`/`multiple_navigation.js`/`non_searchable.js` now import
  `core.js` by that bare specifier instead of the relative path
  `"./core.js"`. A relative import isn't rewritten by a hashed static
  storage (e.g. `ManifestStaticFilesStorage`) the way `{% static %}` is, so
  it would have 404'd in production once `core.js` got renamed to something
  like `core.3b2f1a.js` — the import map resolves it through `static()`
  instead, same as everything else.
- `BaseSelectFilter.media`'s scripts now always carry a CSP nonce when
  `request.csp_nonce` is set — the attribute Django's own CSP middleware
  (6.0+) and the third-party `django-csp` package both use — so a
  `script-src` policy without `'unsafe-inline'` doesn't block the import map
  (inline content) or the module scripts (bare URLs still need one under a
  `'strict-dynamic'` policy). A no-op when neither is in use. Dropped
  `django.forms.Script` (Django 5.2+ only) in favor of always rendering the
  `<script>` tag itself via the same `__html__` escape hatch used for the
  import map — one less Django-version branch, same cross-4.2 support.
