# HydroAgent-XW: Xinwu Water Management Multi-Source Data Agent

HydroAgent-XW is an agent-based water management analysis project for Xinwu District, Wuxi. It is adapted from AutoGIS and extended toward a domain-specific HydroAgent system that can work with local water-environment reports, real-time station data, GIS assets, pipe network materials, and field photos.

## Current MVP

The current version focuses on a safe local MVP without uploading private data.

Implemented capabilities:

- Parse local water-environment reports from DOCX into structured JSONL.
- Parse local real-time water data from XLSX into CSV files.
- Add a HydroAgent query API: `POST /api/hydro/query`.
- Route user questions into report retrieval or time-series/data-dictionary analysis.
- Identify data tables from the real-time data dictionary.
- Explain table usage, field meanings, and possible water-management analysis directions.
- Return `answer`, `sources`, and `debug` fields for explainability.

## Data Privacy

The real Xinwu District documents, spreadsheets, CAD files, PDFs, photos, and generated processed files are private and are not committed to this repository.

Only directory documentation is committed:

```text
data_raw/README.md
data_processed/README.md
```

Private local files should stay under:

```text
data_raw/
data_processed/
```

These paths are excluded by `.gitignore`.

## HydroAgent-XW Roadmap

Planned upgrades:

- Document RAG with vector retrieval.
- Station/device time-series statistics.
- Water-level and device-status anomaly detection.
- GIS analysis for pump gates, rivers, pipe networks, and nearby assets.
- LangGraph-based multi-agent orchestration.
- Evaluation benchmark for router accuracy, retrieval quality, tool correctness, and task success rate.

## Based On

This project is adapted from [AutoGIS](https://github.com/THU-ESIS/AutoGIS), with additional HydroAgent-XW modules for water-management data ingestion, query routing, and domain-specific analysis.

---

# AutoGIS

[ English | [中文](README_zh.md) ]

> A natural-language geospatial analysis platform that retrieves data, generates PyQGIS scripts, executes spatial workflows, and presents results in a web map.

## Overview

AutoGIS turns a geospatial request into an executable workflow. Users describe a task through the command line or web interface; the system identifies intent, prioritizes local data, retrieves public spatial data when needed, generates QGIS/PyQGIS code, and can run that code in a configured QGIS environment. FastAPI and WebSocket services deliver workflow progress and results to the Vue frontend.

AutoGIS is intended for research prototypes, education, and controlled local environments that need to lower the barrier to GIS automation. It is not a hosted service for executing unreviewed LLM-generated code in production.

## Core Capabilities

| Capability | Description |
| --- | --- |
| Natural-language task understanding | Classifies requests as data retrieval only, code generation only, or an end-to-end data and analysis workflow. |
| Local-data first | Searches existing datasets through metadata and vector similarity to avoid unnecessary downloads. |
| Multi-source data retrieval | Supports workflows involving OSM, administrative boundaries, POIs, Sentinel-2, Landsat, and other sources, subject to local configuration and service credentials. |
| PyQGIS code generation | Produces editable analysis scripts using the task, data metadata, and QGIS algorithm references. |
| RAG-assisted repair | Retrieves algorithm documentation and data metadata to help an LLM repair failed code. |
| Web task experience | Provides task submission, real-time progress, catalog browsing, code inspection, and map-based result visualization. |

## System Framework

<p align="center">
<img src="docs/assets/images/autogis-framework.png" alt="AutoGIS agent framework: data agent, code agent, QGIS-GPT, and the execution environment" width="100%">
</p>

AutoGIS connects a data agent and a code agent through data contracts, algorithm contracts, and execution feedback. The geospatial environment provides the available tools, knowledge graph, and memory required for closed-loop analysis.

See [Architecture](docs/ARCHITECTURE.md) for a more detailed technical description.

## QGIS-GPT Model

QGIS-GPT is the specialized model developed for AutoGIS. The following evaluation plot compares average performance and model size across models; QGIS-GPT is positioned on the reported performance-cost Pareto frontier.

<p align="center">
<img src="docs/assets/images/qgis-gpt-performance.png" alt="QGIS-GPT performance and model-size comparison" width="92%">
</p>

**[Download QGIS-GPT from ModelScope](https://www.modelscope.cn/models/itpossible/QGIS-GPT)**

## Demo Videos

The repository includes MP4 demonstrations of the web application and three end-to-end geospatial analysis cases. If your Markdown renderer does not display the embedded player, use the link beneath each video to open the MP4 directly. The videos are configured for Git LFS; after cloning, run `git lfs pull` when the media files are not present locally.

<details open>
<summary><strong>Web Interface</strong></summary>

<video controls preload="metadata" width="100%" src="docs/assets/videos/autogis-web-interface.mp4">Your browser or Markdown renderer does not support embedded MP4 video.</video>

[Open the web interface demo](docs/assets/videos/autogis-web-interface.mp4)

</details>

<details>
<summary><strong>Case 1: Buffer Analysis</strong></summary>

<video controls preload="metadata" width="100%" src="docs/assets/videos/case-1-buffer-analysis.mp4">Your browser or Markdown renderer does not support embedded MP4 video.</video>

[Open the buffer analysis demo](docs/assets/videos/case-1-buffer-analysis.mp4)

</details>

<details>
<summary><strong>Case 2: NDVI Analysis</strong></summary>

<video controls preload="metadata" width="100%" src="docs/assets/videos/case-2-ndvi-analysis.mp4">Your browser or Markdown renderer does not support embedded MP4 video.</video>

[Open the NDVI analysis demo](docs/assets/videos/case-2-ndvi-analysis.mp4)

</details>

<details>
<summary><strong>Case 3: Land-Use Classification</strong></summary>

<video controls preload="metadata" width="100%" src="docs/assets/videos/case-3-land-use-classification.mp4">Your browser or Markdown renderer does not support embedded MP4 video.</video>

[Open the land-use classification demo](docs/assets/videos/case-3-land-use-classification.mp4)

</details>

## Project Layout

```text
.
├── api/                         # FastAPI routes, task services, and WebSocket support
├── core/                        # Data retrieval, geographic queries, metadata, and vector matching
├── data/                        # QGIS algorithm references and data utilities
├── docs/                        # Architecture, setup, release, and media assets
├── scripts/                     # Catalog, retrieval, maintenance, and development utilities
├── spatial_analysis_system/     # Intent, code generation, execution, and optimization workflows
├── tests/                       # Python tests
├── web/                         # Vue 3 + TypeScript frontend
└── run_analysis.py              # Primary command-line entry point
```

See [scripts/README.md](scripts/README.md) for utility script categories, purposes, and restrictions.

The following paths contain runtime output or local data and are not distributed with the source repository: `downloaded_data/`, `output/`, `input/`, `data/training/`, `data/data_catalog.json`, and `data/vector_db.json`. The application creates required output directories when needed.

## Requirements

- Python 3.10 or newer
- Node.js 20 LTS or newer for the web frontend
- QGIS 3.44 or a compatible version when automatic PyQGIS execution is required
- Credentials only for the LLM or data services you choose to enable

QGIS and GDAL binary compatibility depends on the operating system and installation method, so they are intentionally not installed through `requirements.txt`. Use QGIS, OSGeo4W, Conda, or your operating-system package manager to install versions compatible with the selected Python runtime. The current automatic execution setup is primarily intended for a Windows QGIS launcher; other platforms need an equivalent launcher script.

## Quick Start

### 1. Install Python Dependencies

From the repository root:

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Create Local Configuration

The public repository provides credential-free templates only. Copy them and configure your own local values:

```bash
# Windows CMD
copy spatial_analysis_system\config.example.yaml spatial_analysis_system\config.yaml
copy config\local_settings.example.py config\local_settings.py

# macOS / Linux
# cp spatial_analysis_system/config.example.yaml spatial_analysis_system/config.yaml
# cp config/local_settings.example.py config/local_settings.py
```

Configure an LLM service through `llm.api_key` in `spatial_analysis_system/config.yaml` or with the `AUTOGIS_API_KEY` environment variable. Configure additional environment variables or `config/local_settings.py` only when using remote-sensing, map, or USGS sources. Both local files are excluded by `.gitignore` and must never be committed.

To execute generated scripts automatically, configure the following values in `spatial_analysis_system/config.yaml`:

- `qgis.root_path`: QGIS installation root directory.
- `qgis.runqgis_bat_path`: launcher that can execute a PyQGIS script; or
- `qgis.qgis_run_py_path`: wrapper script that runs through the QGIS Python environment.

Use `--no-run` until the QGIS launcher is configured.

### 3. Start the Backend and Frontend

Start the API in one terminal:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Start the frontend in another terminal:

```bash
cd web
npm ci
npm run dev
```

Default local addresses:

- Web interface: `http://127.0.0.1:5173`
- Swagger API documentation: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### 4. Use the Command Line

```bash
# Interactive mode
python run_analysis.py

# Generate a script without executing QGIS
python run_analysis.py --no-run "Download road data for a selected area and create a 500-meter buffer"

# Build a catalog from local data; --no-llm avoids model calls for descriptions
python scripts/build_catalog.py --dir downloaded_data --no-llm
```

Review generated code before execution with someone who understands the data scope, algorithm parameters, and permission boundaries.

## Tests and Build

Run the core tests that do not require live credentials or a complete QGIS installation:

```bash
python -m pytest tests/test_intent_analyzer.py tests/test_code_generator.py
```

Run frontend tests and a production build:

```bash
cd web
npm run test
npm run build
```

Integration tests that require imagery, GDAL, a QGIS launcher, or third-party services should run only in a dedicated environment and must not depend on personal paths, real accounts, or data absent from the repository.

## Configuration and Data Safety

- Never expose API keys, tokens, passwords, or private endpoints in source code, examples, issues, logs, or screenshots.
- Keep downloaded data, analysis output, and local catalogs in ignored directories; distribute data separately only after confirming their licenses and privacy terms.
- The API permits only local development CORS origins by default. Restrict CORS before deploying beyond a trusted network.
- `AUTOGIS_EXTERNAL_OUTPUT_DIR` is mounted only when explicitly configured; never expose untrusted or sensitive directories through the API.
- LLM-generated PyQGIS code can access local files and execute processes. Use least-privilege accounts, isolated data directories, and human review in production environments.

See [SECURITY.md](SECURITY.md) for vulnerability-reporting guidance.

## Known Limitations

- Automatic QGIS execution depends on the local QGIS, Python, and GDAL combination and must be verified for each deployment.
- Data coverage, authentication, rate limits, and licensing are determined by the respective providers.
- LLM output can be inaccurate, non-executable, or semantically unsuitable for a specific GIS task; it does not replace expert review.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Setup and Configuration](docs/SETUP.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)
- [Web Client](web/README.md)
- [Backend API](api/README.md)
- [System Documentation](docs/SYSTEM_DOCUMENTATION.md)

## Acknowledgments and Third-Party Services

AutoGIS is built on open-source projects including QGIS/PyQGIS, FastAPI, Vue, and MapLibre, and can connect to OpenStreetMap, Copernicus/Sentinel, USGS, map, and LLM services. Read each provider's license, attribution requirements, terms of service, and rate limits before use.
