# Architecture

AutoGIS turns a natural-language spatial-analysis request into a data retrieval
and PyQGIS execution workflow. It has three runtime layers:

```text
Vue 3 web client
       |
       | HTTP and WebSocket
       v
FastAPI service (api/)
       |
       v
Workflow engine (spatial_analysis_system/)
       |
       +--> data retrieval and local vector search (core/)
       +--> LLM intent analysis and code generation
       +--> QGIS/PyQGIS execution and error-driven optimization
```

## Components

| Area | Location | Responsibility |
| --- | --- | --- |
| Workflow | `spatial_analysis_system/` | Configuration, task intent, LLM clients, generated-code execution, repair, and catalog building. |
| Retrieval | `core/` | Geographic query parsing, remote data retrieval, metadata generation, embeddings, and local-data matching. |
| API | `api/` | FastAPI routes, task state, file/catalog endpoints, and WebSocket progress notifications. |
| Web client | `web/` | Vue interface, Pinia state, API client, result viewer, and map components. |
| Data support | `data/` | QGIS algorithm reference data and utility scripts. Generated catalogs and vector indexes are deliberately ignored. |

## Request lifecycle

1. The user submits a query through the CLI or `POST /api/analysis/submit`.
2. `IntentAnalyzer` classifies the request as data-only, code-only, or a
   combined task.
3. `VectorLocalFirstGeoQueryEngine` checks the local catalog and fetches data
   only when a suitable local dataset is unavailable.
4. `CodeGenerator` creates PyQGIS code with relevant metadata and algorithm
   context.
5. `CodeExecutor` invokes the configured QGIS launcher when execution is
   enabled.
6. On failure, `CodeOptimizer` can retrieve algorithm documentation and ask an
   LLM to produce a revised script.
7. The API task manager records state and streams progress to connected web
   clients.

## State and artifact boundaries

The following paths are runtime state, not source code: `downloaded_data/`,
`output/`, `input/`, `data/training/`, `data/data_catalog.json`, and
`data/vector_db.json`. They are excluded from Git to avoid publishing large,
private, derived, or license-restricted material. The application creates the
needed output directories at startup.

## Configuration boundary

Committed files must contain no secrets or host-specific paths. Public defaults
live in Python and `spatial_analysis_system/config.example.yaml`; a deployer
copies the example to the ignored `config.yaml`. Optional service credentials
can be supplied by environment variables or the ignored
`config/local_settings.py` file.

## Execution boundary

Generated code can access the local QGIS Python environment and user data. It
is therefore an execution boundary, not merely text generation. Deployments
should use least-privilege service accounts, isolated data directories, and
human review for untrusted or production-impacting requests.
