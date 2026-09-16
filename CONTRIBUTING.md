# Contributing

## Development setup

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

## Tests

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
npm run coverage
```

### Compatibility matrix (tox)

`uv run pytest` above only runs against whatever Django version `uv.lock`
resolved (the newest one satisfying `dependencies`). To check the full
supported range — every Django series in `classifiers`, against the
oldest and newest Python it supports (within this package's own
`requires-python` floor) — run the tox matrix instead:

```bash
uv run tox run-parallel   # every env, in parallel
uv run tox -e py313-dj51  # a single env, e.g. to debug one failure
```

`[tool.tox]` in `pyproject.toml` lists the exact envs. Each one gets its own ephemeral venv (via
[tox-uv](https://github.com/tox-dev/tox-uv), using uv's own Python
builds — `uv python install <version>` once for any you don't have yet)
with only `pytest`/`pytest-django`/`pytest-cov` plus the test-only deps
`tests/*.py` actually import (`django-stubs-ext`, `inline-snapshot`,
`inline-snapshot-django`) and that env's pinned Django — not the full
`dev`/`test` groups — and skips `tests/e2e/` (no Playwright in those
envs). This only tests boundaries (oldest + newest Python per Django
series), not every valid combination — that catches most real breakage
while staying fast. Runs in CI as a separate `compat-matrix.yml`
workflow, alongside the regular `pytest.yml`.
