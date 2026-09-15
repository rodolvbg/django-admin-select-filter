# Changelog

## [0.1.1] - 2026-09-15

### Added

- Added `BaseSelectFilter.media`: a property returning a real
  `django.forms.Media` instance, computed from the filter's own
  configuration — mirrors `ModelAdmin.media`'s own pattern of a `@property`
  building `Media` from instance state. `base.html` now renders
  `{{ spec.media.css }}`/`{{ spec.media.js }}` instead of hardcoding one
  `{% if %}` block per optional JS module.
- `BaseSelectFilter.media`'s scripts now always carry a CSP nonce when
  `request.csp_nonce` is set — the attribute Django's own CSP middleware
  (6.0+) and the third-party `django-csp` package both use — so a
  `script-src` policy without `'unsafe-inline'` doesn't block the import map
  (inline content) or the module scripts (bare URLs still need one under a
  `'strict-dynamic'` policy). A no-op when neither is in use.

### Changed

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
- `async_options.js`/`multiple_navigation.js`/`non_searchable.js` now import
  `core.js` by the bare specifier `"core"` instead of the relative path
  `"./core.js"`, resolved through a `<script type="importmap">` that
  `BaseSelectFilter.media` now also emits. Renders each `<script>` tag
  itself (via `Media`'s `__html__` escape hatch) instead of relying on
  `django.forms.Script`, which only exists from Django 5.2 on — this package
  supports Django >= 4.2.

### Fixed

- A relative JS import (`"./core.js"`) isn't rewritten by a hashed static
  storage (e.g. `ManifestStaticFilesStorage`) the way a template's
  `{% static %}` call is, so it would have 404'd in production once
  `core.js` got renamed to something like `core.3b2f1a.js`. Fixed by the
  import map above, which resolves the bare specifier through `static()`
  instead, same as everything else.
