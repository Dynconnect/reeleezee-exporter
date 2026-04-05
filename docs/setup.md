# Setup Guide

## Prerequisites

- Python 3.8 or later
- A Reeleezee account with API access
- Your Reeleezee username and password

## Installation

### From source (recommended)

```bash
git clone https://github.com/dynconnect/reeleezee-exporter.git
cd reeleezee-exporter
pip install -e .
```

### Using pip directly

```bash
pip install -r requirements.txt
```

## Configuration

### Option 1: Environment file (recommended)

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
REELEEZEE_USERNAME=your_username
REELEEZEE_PASSWORD=your_password
```

### Option 2: Command-line arguments

Pass credentials directly:

```bash
reeleezee-export --username your_username --password your_password
```

### Option 3: Environment variables

```bash
export REELEEZEE_USERNAME=your_username
export REELEEZEE_PASSWORD=your_password
reeleezee-export
```

## Verify Connection

Test that your credentials work:

```bash
reeleezee-explore --username your_username --password your_password
```

This will probe the API and show what administrations and endpoints are
available without downloading any data.

## Running the Export

### Export all data (structured JSON)

```bash
reeleezee-export
```

This creates a directory like `exports/reeleezee_export_20250101_120000/`
with structured JSON files for each administration and data type.

### Download all files (PDFs, scans)

```bash
reeleezee-download
```

This downloads purchase invoice scans, sales invoice PDFs, and offering
PDFs organized by type and year.

### Export to single JSON file

```bash
reeleezee-export --format json
```

### Custom output directory

```bash
reeleezee-export --output-dir /path/to/output
reeleezee-download --output-dir /path/to/files
```

## Viewing Exported Data

After exporting, you can browse the data using the included HTML viewers.

Start a local web server in the project directory:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/viewers/viewer.html` in your browser and
enter the path to your export directory (e.g., `exports/reeleezee_export_20250101_120000/`).

## Web UI (Docker)

The web interface provides a browser-based export experience with real-time
progress tracking. Requires Docker.

### Start

```bash
cd docker
docker compose up --build
```

Open http://localhost:8000 in your browser.

### Services

| Service | Purpose |
|---------|---------|
| **app** | FastAPI web server (port 8000) |
| **worker** | RQ background worker for export jobs |
| **redis** | Job queue and real-time progress pubsub |

### Configuration

Set `SECRET_KEY` in your environment for production use:

```bash
SECRET_KEY=your-random-secret-here docker compose up --build
```

### Stop

```bash
docker compose down       # stop containers
docker compose down -v    # stop and delete data volumes
```

## Troubleshooting

### "Authentication failed: HTTP 401"

- Verify your username and password
- Check that your account has API access enabled
- Only one session per account is allowed - close other sessions first

### "No administrations found"

- Your account may not have any administrations assigned
- Contact your Reeleezee administrator

### Slow downloads

- Large exports can take significant time (30+ minutes for full data)
- The export files endpoint may be slow for certain years
- Files that were already downloaded are automatically skipped on re-run

### "Connection refused" or timeout errors

- Check your internet connection
- Verify that `portal.reeleezee.nl` is accessible
- The API may be temporarily unavailable
