# AutoGIS Web Client

The AutoGIS web client is a Vue 3 and TypeScript application for submitting
analysis requests, following task progress, browsing the data catalog, and
viewing vector or raster results on a map.

## Prerequisites

- Node.js 20 LTS or newer
- A running AutoGIS API service, normally at `http://localhost:8000`

## Commands

```bash
npm ci
npm run dev
npm run test
npm run build
```

The Vite development server defaults to `http://localhost:5173`. The backend
CORS configuration permits this address by default.

## Production build

`npm run build` writes static assets to `web/dist/`. Serve that directory with
your chosen web server and configure its API proxy or frontend API base URL for
the deployed AutoGIS backend.

## Notes for contributors

- Do not place API keys or local filesystem paths in frontend source files.
- Treat paths returned by the backend as untrusted display data; the backend
  remains responsible for file authorization.
- Keep map rendering changes testable with the existing Vitest suite where
  possible.
