# Contributing to AutoGIS

Thank you for considering a contribution. Small, focused pull requests are
easier to review and release than broad, mixed changes.

## Before you start

- Open an issue first for new data sources, workflow changes, or UI redesigns.
- Do not commit API keys, service tokens, downloaded imagery, task outputs, or
  local QGIS paths.
- Keep user-facing strings and new documentation in English. The maintainer is
  currently preparing the Chinese README for English translation.

## Development setup

1. Create a Python 3.10+ virtual environment and install `requirements.txt`.
2. Copy `spatial_analysis_system/config.example.yaml` to `config.yaml` and
   provide only values required by the feature being worked on.
3. Install the frontend dependencies with `npm ci` in `web/`.
4. Use a QGIS installation compatible with the configured launcher for
   end-to-end PyQGIS execution.

## Pull request checklist

- Explain the user-visible behavior and any configuration migration.
- Add or update focused tests when practical.
- Run the applicable Python tests and `npm run build` in `web/`.
- Update `README.md` or a document under `docs/` when setup, APIs, or behavior
  change.
- Confirm that generated files and credentials do not appear in the diff.

## Code style

Follow the surrounding style, keep imports explicit, and use descriptive names.
Avoid unrelated formatting changes. New public APIs should include concise type
annotations and documentation.
