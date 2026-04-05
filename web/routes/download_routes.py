"""Download routes: ZIP generation and streaming."""

import json
import os
from pathlib import Path

import redis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import config
from ..auth import get_current_session
from ..database import get_db

router = APIRouter(tags=["download"])


@router.post("/jobs/{job_id}/download")
def start_download(job_id: str, session: dict = Depends(get_current_session)):
    """Start ZIP generation for a completed job."""
    with get_db() as db:
        job_row = db.execute(
            "SELECT * FROM jobs WHERE id = ? AND session_id = ?",
            (job_id, session["id"]),
        ).fetchone()
    if not job_row:
        raise HTTPException(status_code=404, detail="Job not found")

    data_dir = Path(job_row["data_dir"])
    zip_path = data_dir / f"{job_id}.zip"

    if zip_path.exists():
        return {"zip_ready": True, "size_mb": round(zip_path.stat().st_size / (1024 * 1024), 1)}

    # Enqueue ZIP generation
    try:
        r = redis.from_url(config.REDIS_URL)
        from rq import Queue
        q = Queue("downloads", connection=r)
        q.enqueue(
            "web.workers.download_job.generate_zip",
            job_id,
            job_timeout="1h",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start ZIP generation: {e}")

    return {"zip_ready": False, "message": "ZIP generation started"}


@router.get("/jobs/{job_id}/download")
def get_download(job_id: str, session: dict = Depends(get_current_session)):
    """Download the ZIP file if ready, or return status."""
    with get_db() as db:
        job_row = db.execute(
            "SELECT data_dir FROM jobs WHERE id = ? AND session_id = ?",
            (job_id, session["id"]),
        ).fetchone()
    if not job_row:
        raise HTTPException(status_code=404, detail="Job not found")

    data_dir = Path(job_row["data_dir"])
    zip_path = data_dir / f"{job_id}.zip"

    if not zip_path.exists():
        return {"zip_ready": False, "message": "ZIP not yet generated. POST to start generation."}

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"reeleezee_export_{job_id[:8]}.zip",
    )
