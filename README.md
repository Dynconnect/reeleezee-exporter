# reeleezee-exporter

[![Lint & Test](https://github.com/dynconnect/reeleezee-exporter/actions/workflows/lint.yml/badge.svg)](https://github.com/dynconnect/reeleezee-exporter/actions/workflows/lint.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**The first open-source tool to fully export all your data from [Reeleezee](https://www.exact.com/nl/software/exact-reeleezee) (now Exact Reeleezee), a Dutch accounting platform.**

Reeleezee does not provide a built-in full data export. This tool connects to their REST API and downloads everything: invoices, customers, vendors, products, bank data, PDF documents, scans, and audit files.

Available as a **CLI tool** for scripting and automation, or as a **web application** (Docker) with a browser-based UI for interactive exports with real-time progress tracking.

> **Author:** Sinisa Devcic / [Dynconnect](https://dynconnect.com)

## Features

- **Full data export** — sales invoices (with line items), purchase invoices, customers, vendors, products, offerings, bank imports, bank statements, ledger accounts, and more
- **File downloads** — purchase invoice scans (original JPG/PDF), sales invoice PDFs, offering/quote PDFs
- **Administration exports** — audit files (CLAIR, XAF), trial balances, and financial reports for all available years
- **Year selection** — choose which years to export, with automatic detection of years that contain data
- **Web UI** — browser-based interface with login, export configuration, live progress (SSE), data browser, file browser, and ZIP download
- **Docker** — one command to run: `docker compose up --build`
- **Auto-discovery** — automatically finds all administrations in your account
- **Incremental downloads** — re-running skips already-downloaded files
- **Resume** — failed exports can be resumed from the last checkpoint
- **Structured output** — organized JSON files per administration and data type
- **Credentials via .env** — no credentials in code, supports `.env` files

## Quick Start

### CLI

```bash
git clone https://github.com/dynconnect/reeleezee-exporter.git
cd reeleezee-exporter
pip install -e .

# Configure credentials
cp .env.example .env
# Edit .env with your Reeleezee username and password

# Export all data
reeleezee-export

# Download all files (PDFs, scans)
reeleezee-download
```

### Web UI (Docker)

```bash
cd docker
docker compose up --build

# Open http://localhost:8000
```

## Installation

### pip (CLI tools)

```bash
pip install -e .
```

### pip with web dependencies

```bash
pip install -e ".[web]"
```

### Without installing

```bash
pip install -r requirements.txt
python -m reeleezee_exporter.export_data --username USER --password PASS
```

## Usage

### CLI: Export all data

```bash
# Using .env file (recommended)
reeleezee-export

# With explicit credentials
reeleezee-export --username YOUR_USER --password YOUR_PASS

# Custom output directory
reeleezee-export --output-dir ./my_export

# Single JSON file instead of structured
reeleezee-export --format json
```

### CLI: Download all files

```bash
# Download all PDFs and scans
reeleezee-download

# Custom output directory
reeleezee-download --output-dir ./my_files
```

### CLI: Explore the API

```bash
# Discover available endpoints and data
reeleezee-explore
```

### Web UI

```bash
cd docker
docker compose up --build
```

Open http://localhost:8000 in your browser:

1. **Login** with your Reeleezee credentials
2. **Select years** — years with data are automatically detected and highlighted
3. **Select data types** — choose which endpoints and file types to export
4. **Start export** — watch real-time progress via Server-Sent Events
5. **Browse data** — view exported data in paginated tables while export runs
6. **Browse files** — view downloaded PDFs and scans
7. **Download ZIP** — download the complete export as a ZIP archive

### View exported data (static viewers)

```bash
python -m http.server 8000
# Open http://localhost:8000/viewers/viewer_advanced.html
```

## What Gets Exported

### Structured Data (JSON)

| Data Type | Description |
|-----------|-------------|
| Administrations | Administration details and settings |
| Sales Invoices | All outgoing invoices with full detail (43+ fields) |
| Sales Invoice Lines | Individual line items per invoice |
| Purchase Invoices | All incoming invoices with full detail |
| Customers | Customer records |
| Vendors | Vendor/supplier records |
| Products | Product catalog |
| Offerings | Quotes and offerings |
| Relations | Combined customer/vendor relations |
| Addresses | All addresses |
| Accounts | Ledger accounts |
| Bank Imports | Bank import file records |
| Bank Statements | Bank statement records |
| Documents | Document metadata |
| Export Files | Audit files, trial balances (CLAIR, XAF formats) |

### Downloaded Files

| File Type | Source | Format |
|-----------|--------|--------|
| Purchase invoice scans | Uploaded originals | JPG, PDF, PNG |
| Sales invoice PDFs | Generated by Reeleezee | PDF |
| Offering PDFs | Generated by Reeleezee | PDF |

## Output Structure

```
exports/reeleezee_export_20250101_120000/
    index.json
    {administration_id}/
        index.json
        administration.json
        sales_invoices.json
        sales_invoice_lines.json
        purchase_invoices.json
        customers.json
        vendors.json
        products.json
        offerings.json
        bank_imports.json
        bank_statements.json
        exports.json
        export_files.json
```

## Configuration

Credentials can be provided in three ways (in order of precedence):

1. **Command-line arguments**: `--username USER --password PASS`
2. **Environment variables**: `REELEEZEE_USERNAME` and `REELEEZEE_PASSWORD`
3. **`.env` file**: Copy `.env.example` to `.env` and fill in values

### Web UI configuration

For Docker deployments, set `SECRET_KEY` for production:

```bash
SECRET_KEY=your-random-secret docker compose up --build
```

See [.env.example](.env.example) for all available settings.

## Docker

The web UI runs as three Docker containers:

| Service | Purpose |
|---------|---------|
| **app** | FastAPI web server (port 8000) |
| **worker** | RQ background worker for async export jobs |
| **redis** | Job queue and real-time progress (pubsub) |

```bash
cd docker

# Start
docker compose up --build

# Start in background
docker compose up --build -d

# Stop
docker compose down

# Stop and remove data
docker compose down -v
```

## Testing

```bash
pip install -e ".[web]"
pip install pytest

# Run all tests
pytest tests/ -v

# Run only CLI tests
pytest tests/test_client.py tests/test_export_data.py -v

# Run only web tests
pytest tests/test_web.py -v
```

## API

This tool uses the Reeleezee REST API at `https://portal.reeleezee.nl/api/v1/` with HTTP Basic Authentication. See [docs/api-endpoints.md](docs/api-endpoints.md) for the complete list of discovered endpoints.

Key API characteristics:
- OData v4 format with `@odata.nextLink` pagination
- Only one concurrent session per account
- Default page size of 1000 items
- Date filtering via `$filter=Date ge ... and Date lt ...`

## Documentation

- [Setup Guide](docs/setup.md) — Installation and configuration
- [Architecture](docs/architecture.md) — Code structure and design
- [API Endpoints](docs/api-endpoints.md) — All discovered Reeleezee API endpoints
- [Contributing](CONTRIBUTING.md) — How to contribute

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)

Copyright (c) 2025 Sinisa Devcic / [Dynconnect](https://dynconnect.com)
