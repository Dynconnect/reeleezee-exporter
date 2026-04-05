# Architecture

## Overview

reeleezee-exporter is structured as a Python package with three main tools:

```
src/reeleezee_exporter/
    __init__.py          # Package metadata
    client.py            # Low-level API client (auth, pagination, downloads)
    export_data.py       # Full data export to structured JSON
    download_files.py    # Binary file downloader (PDFs, scans)
    explore_api.py       # API endpoint discovery tool
    generate_viewer.py   # HTML viewer generator
```

## Component Diagram

```
                    +------------------+
                    |   CLI (argparse) |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v------+  +----v--------+
     | export_data |  | download_   |  | explore_api |
     |             |  | files       |  |             |
     +--------+----+  +------+------+  +------+------+
              |              |                |
              +--------------+----------------+
                             |
                    +--------v---------+
                    | ReeleezeeClient  |
                    | (client.py)      |
                    +--------+---------+
                             |
                    +--------v---------+
                    | Reeleezee REST   |
                    | API (OData)      |
                    | portal.reeleezee |
                    | .nl/api/v1/      |
                    +------------------+
```

## ReeleezeeClient (client.py)

The foundation layer that handles:

- **Authentication**: HTTP Basic Auth with username/password
- **Session management**: Persistent `requests.Session` with auth headers
- **Pagination**: OData-style pagination following `@odata.nextLink`
- **Binary downloads**: File content retrieval for PDFs and scans

The client is intentionally simple. It does not cache or retry.
This makes it predictable and easy to debug.

## Data Export (export_data.py)

The main export tool that orchestrates the full data extraction:

1. Discovers all administrations
2. For each administration:
   - Fetches administration details
   - Downloads export files (audit files, trial balances)
   - Fetches all related data via paginated endpoints
   - Enriches sales invoices with line items
   - Enriches purchase invoices with full detail

Output is saved either as structured JSON (one file per data type per
administration) or a single monolithic JSON file.

## File Downloader (download_files.py)

Downloads binary files that the API serves:

- Purchase invoice scans via `Files/{id}/Download`
- Sales invoice PDFs via `SalesInvoices/{id}/Download`
- Offering PDFs via `Offerings/{id}/Download`

Files are organized by type and year. Each category gets an `index.json`
metadata file tracking download status.

Supports incremental downloads: already-downloaded files are skipped based
on file existence and size.

## API Explorer (explore_api.py)

A diagnostic tool for understanding the API. Probes known endpoints,
fetches OData metadata, and reports available entity sets. Useful when
the API adds new endpoints or when debugging connectivity issues.

## HTML Viewers (viewers/)

Browser-based viewers for the exported JSON data. Two variants:

- **viewer.html**: Table-based viewer for flat data files
- **viewer_advanced.html**: Year-based viewer with invoice detail, line items,
  and bank import correlation

Both are static HTML files that load JSON data via `fetch()`. They require
a local web server (e.g., `python -m http.server`) because browsers block
`fetch()` from `file://` URLs.

## Web UI (web/)

A browser-based interface for interactive exports with async processing.

```
web/
    app.py                 # FastAPI application factory
    config.py              # Settings (Redis, DB, secret key)
    database.py            # SQLite schema and helpers
    auth.py                # Session management, Fernet credential encryption
    schemas.py             # Pydantic request/response models
    routes/
        auth_routes.py     # POST /api/login, /api/logout, GET /api/me
        admin_routes.py    # GET /api/administrations/{id}/years[/detailed]
        job_routes.py      # CRUD jobs + SSE progress stream
        data_routes.py     # Browse exported JSON data + serve files
        download_routes.py # ZIP generation + streaming download
    workers/
        export_job.py      # Background export (wraps ReeleezeeExporter)
        download_job.py    # Background ZIP generation
    static/
        index.html         # SPA shell
        app.js             # Vanilla JS app (hash routing)
        style.css           # UI styles

docker/
    Dockerfile             # Single image for app + worker
    docker-compose.yml     # app + worker + redis (3 services)
```

### Web Architecture

```
Browser  <-->  FastAPI (app container, port 8000)
                  |
                  +-- SQLite (job state, sessions)
                  |
                  +-- Redis (job queue + pubsub for SSE)
                  |
                  +-- RQ Worker (worker container)
                        |
                        +-- ReeleezeeClient
                        +-- ReeleezeeExporter
                        +-- ReeleezeeFileDownloader
                        |
                        +-- Filesystem (data/)
```

### Job System

1. User logs in via web UI (credentials encrypted with Fernet, stored in SQLite session)
2. User selects years, data types, and file downloads
3. POST /api/jobs creates a job row and enqueues it on Redis via RQ
4. Worker picks up the job, exports data endpoint-by-endpoint
5. Each completed endpoint is saved to disk immediately (progressive availability)
6. Progress published via Redis pubsub, streamed to browser via SSE
7. User can browse partial results while export is still running
8. Completed exports can be downloaded as ZIP

### Security

- Credentials encrypted at rest with Fernet (AES-128-CBC)
- Session ID in signed httponly cookie
- Credentials copied to job row at creation (worker independent of session)
- 24-hour session expiry
- Path traversal protection on file serving

## Authentication

The Reeleezee API uses HTTP Basic Authentication:

```
Authorization: Basic base64(username:password)
```

Credentials can be provided via:
1. Command-line arguments (`--username`, `--password`)
2. Environment variables (`REELEEZEE_USERNAME`, `REELEEZEE_PASSWORD`)
3. `.env` file (loaded via python-dotenv)

## Data Flow

```
Reeleezee API  -->  ReeleezeeClient  -->  ReeleezeeExporter  -->  JSON files
                                     -->  FileDownloader     -->  PDF/JPG files
```

All API responses follow the OData format:
```json
{
  "value": [...],
  "@odata.nextLink": "https://..."
}
```

Pagination is handled transparently by `client.get_paginated()`.
