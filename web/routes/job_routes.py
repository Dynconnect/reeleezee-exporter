"""Job management routes: create, list, get, delete, SSE progress."""

import asyncio
import json
import uuid
from datetime import datetime

import redis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .. import config
from ..auth import get_current_session
from ..database import get_db, row_to_dict
from ..schemas import JobCreateRequest

router = APIRouter(tags=["jobs"])


# Default endpoints to export when none specified
DEFAULT_DATA_ENDPOINTS = [
    "salesinvoices", "purchaseinvoices", "customers", "vendors",
    "products", "bankimports", "bankstatements", "offerings",
    "relations", "addresses", "accounts", "documents",
    "purchaseinvoicescans",
]

DEFAULT_FILE_ENDPOINTS = [
    "purchase_scans", "sales_pdfs", "offering_pdfs",
]


@router.post("/jobs")
def create_job(body: JobCreateRequest, session: dict = Depends(get_current_session)):
    """Create a new export job and enqueue it for processing."""
    admins = session.get("administrations", "[]")
    if isinstance(admins, str):
        admins = json.loads(admins)

    # Find the requested administration
    admin = None
    for a in admins:
        if (a.get("id") or a.get("Id")) == body.admin_id:
            admin = a
            break
    if not admin:
        raise HTTPException(status_code=404, detail="Administration not found")

    admin_name = admin.get("Name") or admin.get("name") or body.admin_id

    # Determine endpoints
    endpoints = body.endpoints
    if not endpoints:
        if body.job_type == "data":
            endpoints = DEFAULT_DATA_ENDPOINTS
        elif body.job_type == "files":
            endpoints = DEFAULT_FILE_ENDPOINTS
        else:  # both
            endpoints = DEFAULT_DATA_ENDPOINTS + DEFAULT_FILE_ENDPOINTS

    job_id = str(uuid.uuid4())
    data_dir = f"{config.DATA_DIR}/{job_id}"

    with get_db() as db:
        db.execute(
            """INSERT INTO jobs
               (id, session_id, admin_id, admin_name, job_type, endpoints,
                years, data_dir, encrypted_credentials)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, session["id"], body.admin_id, admin_name,
             body.job_type, json.dumps(endpoints), json.dumps(body.years),
             data_dir, session["encrypted_credentials"]),
        )

        # Create step rows for tracking
        for ep in endpoints:
            db.execute(
                "INSERT INTO job_steps (job_id, step_name) VALUES (?, ?)",
                (job_id, ep),
            )

    # Enqueue the job
    try:
        r = redis.from_url(config.REDIS_URL)
        from rq import Queue
        q = Queue("exports", connection=r)
        q.enqueue(
            "web.workers.export_job.run_export_job",
            job_id,
            job_timeout="4h",
        )
    except Exception as e:
        # Update job status to failed if we can't enqueue
        with get_db() as db:
            db.execute(
                "UPDATE jobs SET status = 'failed', error_message = ? WHERE id = ?",
                (f"Failed to enqueue: {e}", job_id),
            )
        raise HTTPException(status_code=500, detail=f"Failed to enqueue job: {e}")

    return {"id": job_id, "status": "pending"}


@router.get("/jobs")
def list_jobs(session: dict = Depends(get_current_session)):
    """List all jobs for the current session."""
    with get_db() as db:
        rows = db.execute(
            """SELECT * FROM jobs WHERE session_id = ?
               ORDER BY created_at DESC""",
            (session["id"],),
        ).fetchall()

    return [row_to_dict(r) for r in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, session: dict = Depends(get_current_session)):
    """Get job detail including step progress."""
    with get_db() as db:
        job_row = db.execute(
            "SELECT * FROM jobs WHERE id = ? AND session_id = ?",
            (job_id, session["id"]),
        ).fetchone()
        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

        steps = db.execute(
            "SELECT * FROM job_steps WHERE job_id = ? ORDER BY id",
            (job_id,),
        ).fetchall()

    job = row_to_dict(job_row)
    job["steps"] = [dict(s) for s in steps]
    return job


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str, session: dict = Depends(get_current_session)):
    """Cancel a running or pending job."""
    with get_db() as db:
        job_row = db.execute(
            "SELECT * FROM jobs WHERE id = ? AND session_id = ?",
            (job_id, session["id"]),
        ).fetchone()
        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_row["status"] in ("completed", "cancelled"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status '{job_row['status']}'",
            )

        db.execute(
            "UPDATE jobs SET status = 'cancelled' WHERE id = ?",
            (job_id,),
        )

    # Publish cancellation event
    try:
        r = redis.from_url(config.REDIS_URL)
        r.publish(f"job:{job_id}:control", "cancel")
    except Exception:
        pass

    return {"message": "Job cancelled"}


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, session: dict = Depends(get_current_session)):
    """Resume a failed job from its last checkpoint."""
    with get_db() as db:
        job_row = db.execute(
            "SELECT * FROM jobs WHERE id = ? AND session_id = ?",
            (job_id, session["id"]),
        ).fetchone()
        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_row["status"] not in ("failed",):
            raise HTTPException(
                status_code=400,
                detail=f"Can only resume failed jobs, current status: '{job_row['status']}'",
            )

        db.execute(
            """UPDATE jobs SET status = 'pending', error_message = NULL,
               error_traceback = NULL WHERE id = ?""",
            (job_id,),
        )

    # Re-enqueue
    try:
        r = redis.from_url(config.REDIS_URL)
        from rq import Queue
        q = Queue("exports", connection=r)
        q.enqueue(
            "web.workers.export_job.run_export_job",
            job_id,
            job_timeout="4h",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to re-enqueue: {e}")

    return {"message": "Job resumed", "id": job_id}


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, session: dict = Depends(get_current_session)):
    """SSE endpoint for real-time job progress updates."""
    # Verify job exists and belongs to session
    with get_db() as db:
        job_row = db.execute(
            "SELECT id, status FROM jobs WHERE id = ? AND session_id = ?",
            (job_id, session["id"]),
        ).fetchone()
        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        # Send current state first
        with get_db() as db:
            job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            steps = db.execute(
                "SELECT * FROM job_steps WHERE job_id = ? ORDER BY id",
                (job_id,),
            ).fetchall()

        job_dict = row_to_dict(dict(job))
        job_dict["steps"] = [dict(s) for s in steps]
        yield f"event: state\ndata: {json.dumps(job_dict)}\n\n"

        # If already terminal, done
        if job["status"] in ("completed", "failed", "cancelled"):
            return

        # Subscribe to Redis pubsub for live updates
        try:
            r = redis.from_url(config.REDIS_URL)
            pubsub = r.pubsub()
            pubsub.subscribe(f"job:{job_id}:progress")

            while True:
                message = pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"event: progress\ndata: {data}\n\n"

                    # Check for terminal events
                    try:
                        parsed = json.loads(data)
                        if parsed.get("status") in ("completed", "failed", "cancelled"):
                            break
                    except json.JSONDecodeError:
                        pass
                else:
                    # Send keepalive
                    yield ": keepalive\n\n"

                await asyncio.sleep(0.1)

            pubsub.unsubscribe()
            pubsub.close()
        except Exception:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
