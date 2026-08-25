# Utility Scripts

This directory contains executable utilities that support AutoGIS development
and local operations. The repository root intentionally retains only
`run_analysis.py`, the primary user-facing command-line entry point.

## Common commands

| Script | Purpose |
| --- | --- |
| `build_catalog.py` | Scan local GIS data and build the ignored catalog and vector index. |
| `query_data.py` | Run local-first geographic data retrieval from the command line. |
| `generate_beijing_training_data.py` | Create the ignored Beijing land-use training sample GeoJSON. |

Run common commands from the repository root:

```bash
python scripts/build_catalog.py --dir downloaded_data --no-llm
python scripts/query_data.py "Find roads in a selected area" --no-llm
python scripts/generate_beijing_training_data.py
```

## Restricted utilities

- `maintenance/` contains scripts that modify generated catalogs or local data.
  Review the source and make a backup before running them.
- `development/` contains manual diagnostics; these are not part of the test
  suite. `debug_data_download.py` uses `AUTOGIS_API_BASE_URL` and defaults to
  `http://127.0.0.1:8000`.
- `migrations/` contains historical one-off source migration scripts. They are
  retained for traceability, must not run as part of normal setup, and should be
  reviewed against the current code before use.
