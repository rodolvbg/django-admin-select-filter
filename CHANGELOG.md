# Changelog

## [Unreleased]

### Added

- Compatibility matrix via tox (`[tool.tox]` in `pyproject.toml`, using
  [tox-uv](https://github.com/tox-dev/tox-uv)): tests every Django series
  in `classifiers` (4.2 through 5.1) against its oldest and newest
  supported Python, within this package's own floor. `uv run tox run`
  locally, a separate `compat-matrix.yml` CI workflow.
- `.github/workflows/pre-commit.yml`.

### Changed

- Test config moved from a standalone `pytest.ini` into
  `[tool.pytest.ini_options]` in `pyproject.toml`.
- `release.yml` now builds with `uv build` instead of `pip install build` +
  `python -m build`, matching the rest of the uv-centric tooling.

### Fixed

- The test suite constructed a list filter's `params` dict hardcoded to
  Django 5.0+'s shape (`request.GET.lists()`-style, one list per key).
  Real Django < 5.0 passes a single scalar per key instead
  (`request.GET.items()`-style) — the filter classes themselves never
  build this dict, they only read whatever `SimpleListFilter.__init__`
  populates from it, so the mismatch was entirely in the tests, not in
  `filters.py`/`views.py`/`urls.py`. It silently produced empty querysets
  in `test_filters.py` under Django 4.2, caught by the new compatibility
  matrix. Fixed with a single `autouse` fixture adapting the shape at
  the one shared choke point, rather than touching ~20 call sites.

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
