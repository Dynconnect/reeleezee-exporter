"""Data browsing routes: list and serve exported data and files."""

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import config
from ..auth import get_current_session
from ..database import get_db

router = APIRouter(tags=["data"])


def _get_job_dir(job_id: str, session: dict) -> Path:
    """Verify job belongs to session and return its data directory."""
    with get_db() as db:
        row = db.execute(
            "SELECT data_dir FROM jobs WHERE id = ? AND session_id = ?",
            (job_id, session["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    data_dir = Path(row["data_dir"])
    if not data_dir.exists():
        raise HTTPException(status_code=404, detail="Export data not yet available")
    return data_dir


@router.get("/jobs/{job_id}/data")
def list_data(job_id: str, session: dict = Depends(get_current_session)):
    """List available data files for a job."""
    data_dir = _get_job_dir(job_id, session)

    files = {}
    for json_file in data_dir.rglob("*.json"):
        rel_path = json_file.relative_to(data_dir)
        # Skip index files
        if json_file.name == "index.json":
            continue
        try:
            with open(json_file, "r") as f:
                meta = json.load(f)
            files[str(rel_path)] = {
                "path": str(rel_path),
                "type": meta.get("type", json_file.stem),
                "count": meta.get("count", 0),
                "size_kb": round(json_file.stat().st_size / 1024, 1),
                "exported_at": meta.get("exported_at"),
            }
        except (json.JSONDecodeError, OSError):
            files[str(rel_path)] = {
                "path": str(rel_path),
                "type": json_file.stem,
                "size_kb": round(json_file.stat().st_size / 1024, 1),
            }

    return {"job_id": job_id, "files": files}


@router.get("/jobs/{job_id}/data/{data_type}")
def get_data(
    job_id: str,
    data_type: str,
    page: int = 1,
    per_page: int = 50,
    session: dict = Depends(get_current_session),
):
    """Return paginated JSON data for a specific data type."""
    data_dir = _get_job_dir(job_id, session)

    # Map step names (no underscore) to filenames (with underscore)
    name_map = {
        "salesinvoices": "sales_invoices",
        "purchaseinvoices": "purchase_invoices",
        "salesinvoicelines": "sales_invoice_lines",
        "salesinvoices_detail": "sales_invoices",
        "purchaseinvoices_detail": "purchase_invoices",
        "bankimports": "bank_imports",
        "bankstatements": "bank_statements",
        "purchaseinvoicescans": "purchase_invoice_scans",
    }

    # Build list of candidate filenames to search for
    candidates = [
        data_type,
        data_type.replace("-", "_"),
        name_map.get(data_type, ""),
    ]

    target_file = None
    for json_file in data_dir.rglob("*.json"):
        if json_file.name == "index.json":
            continue
        if json_file.stem in candidates:
            target_file = json_file
            break

    if not target_file or not target_file.exists():
        raise HTTPException(status_code=404, detail=f"Data type '{data_type}' not found")

    try:
        with open(target_file, "r") as f:
            content = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading data: {e}")

    # Extract items array
    items = content.get("data", content) if isinstance(content, dict) else content
    if not isinstance(items, list):
        items = [items]

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]

    return {
        "type": data_type,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "data": page_items,
    }


@router.get("/jobs/{job_id}/files")
def list_files(job_id: str, session: dict = Depends(get_current_session)):
    """List all downloaded files (PDFs, images) for a job."""
    data_dir = _get_job_dir(job_id, session)

    files = []
    file_extensions = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".bin"}

    for f in data_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in file_extensions:
            rel_path = f.relative_to(data_dir)
            files.append({
                "path": str(rel_path),
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "type": f.suffix.lower().lstrip("."),
            })

    return {"job_id": job_id, "files": files, "total": len(files)}


@router.get("/jobs/{job_id}/files/{file_path:path}")
def serve_file(
    job_id: str,
    file_path: str,
    session: dict = Depends(get_current_session),
):
    """Serve an individual downloaded file."""
    data_dir = _get_job_dir(job_id, session)

    target = data_dir / file_path
    # Prevent path traversal
    try:
        target.resolve().relative_to(data_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(target))
