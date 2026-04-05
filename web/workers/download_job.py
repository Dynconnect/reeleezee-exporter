"""Background worker for ZIP generation."""

import os
import tempfile
import zipfile
from pathlib import Path

from web import config


def generate_zip(job_id: str):
    """Generate a ZIP archive of all exported data for a job."""
    from web.database import get_db

    with get_db() as db:
        job = db.execute("SELECT data_dir FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return

    data_dir = Path(job["data_dir"])
    if not data_dir.exists():
        return

    zip_path = data_dir / f"{job_id}.zip"
    if zip_path.exists():
        return  # Already generated

    # Create ZIP in temp file, then move atomically
    fd, tmp_path = tempfile.mkstemp(dir=str(data_dir), suffix=".zip.tmp")
    os.close(fd)

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(data_dir):
                for filename in files:
                    filepath = Path(root) / filename
                    # Skip the ZIP itself and temp files
                    if filepath.suffix in (".tmp", ".zip"):
                        continue
                    arcname = filepath.relative_to(data_dir)
                    zf.write(filepath, arcname)

        os.replace(tmp_path, str(zip_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
