# Setup Guide

This guide describes a development setup. QGIS execution is environment
dependent; the current launcher configuration is primarily designed for a
Windows QGIS installation.

## Prerequisites

- Python 3.10 or newer
- Node.js 20 LTS or newer for the web client
- QGIS 3.44 or a compatible installation for generated-script execution
- Credentials for only the remote services you intend to use

## Python environment

From the repository root:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` intentionally does not install QGIS or GDAL. Install those
through QGIS, OSGeo4W, Conda, or the operating-system package manager so their
native libraries match the selected Python runtime.

## Local configuration

```bash
copy spatial_analysis_system\config.example.yaml spatial_analysis_system\config.yaml
copy config\local_settings.example.py config\local_settings.py
```

On macOS or Linux, use `cp` in place of `copy`. Both destination files are
ignored by Git. At minimum, configure an LLM API key by either setting
`llm.api_key` in `config.yaml` or exporting `AUTOGIS_API_KEY`. Configure
`qgis.root_path` and a valid `qgis.runqgis_bat_path` or `qgis.qgis_run_py_path`
before enabling automatic script execution.

Additional optional environment variables include `AMAP_API_KEY`,
`SENTINEL_HUB_CLIENT_ID`, `SENTINEL_HUB_CLIENT_SECRET`, `USGS_USERNAME`,
`USGS_TOKEN`, `QWEN_API_KEY`, `DASHSCOPE_API_KEY`, and
`AUTOGIS_EXTERNAL_OUTPUT_DIR`.

## Run the services

Start the API from the repository root:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Then start the web client in a second terminal:

```bash
cd web
npm ci
npm run dev
```

The API documentation is available at `http://127.0.0.1:8000/docs` and the
web client normally runs at `http://127.0.0.1:5173`.

## CLI and catalog utilities

```bash
python run_analysis.py --no-run "Download road data for a selected area"
python scripts/build_catalog.py --dir downloaded_data --no-llm
python -m pytest tests/test_code_generator.py tests/test_intent_analyzer.py
```

Use `--no-run` until the QGIS launcher is configured and the generated script
has been reviewed.
