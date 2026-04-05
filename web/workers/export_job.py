"""Background worker for export jobs.

Wraps the existing ReeleezeeExporter and ReeleezeeFileDownloader
to run endpoint-by-endpoint with progress reporting.
"""

import json
import os
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

import redis

from web import config
from web.auth import decrypt_credentials
from web.database import get_db


def _publish(r, job_id: str, event: dict):
    """Publish a progress event to Redis pubsub."""
    try:
        r.publish(f"job:{job_id}:progress", json.dumps(event))
    except Exception:
        pass


def _update_job(job_id: str, **fields):
    """Update job fields in the database."""
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with get_db() as db:
        db.execute(f"UPDATE jobs SET {sets} WHERE id = ?", values)


def _update_step(job_id: str, step_name: str, **fields):
    """Update a job step in the database."""
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id, step_name]
    with get_db() as db:
        db.execute(
            f"UPDATE job_steps SET {sets} WHERE job_id = ? AND step_name = ?",
            values,
        )


def _atomic_write_json(filepath: Path, data):
    """Write JSON atomically via temp file + rename."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(filepath.parent), suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(filepath))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _is_cancelled(r, job_id: str) -> bool:
    """Check if the job has been cancelled."""
    with get_db() as db:
        row = db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row and row["status"] == "cancelled"


def run_export_job(job_id: str):
    """Main export job entry point. Called by RQ worker."""
    r = redis.from_url(config.REDIS_URL)

    # Load job from database
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return

    if job["status"] == "cancelled":
        return

    try:
        # Decrypt credentials and create client
        creds = decrypt_credentials(job["encrypted_credentials"])
        from reeleezee_exporter.client import ReeleezeeClient
        client = ReeleezeeClient(creds["username"], creds["password"])

        admin_id = job["admin_id"]
        admin_name = job["admin_name"]
        job_type = job["job_type"]
        endpoints = json.loads(job["endpoints"])
        completed_steps = json.loads(job["completed_steps"])
        years = json.loads(job["years"]) if job["years"] else []
        data_dir = Path(job["data_dir"])
        admin_dir = data_dir / admin_id
        admin_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow().isoformat()
        _update_job(job_id, status="running", started_at=now)
        _publish(r, job_id, {"status": "running", "started_at": now})

        # Data export endpoints
        data_endpoints = [
            ("relations", "Relations"),
            ("addresses", "Addresses"),
            ("documents", "Documents"),
            ("salesinvoices", "SalesInvoices"),
            ("purchaseinvoices", "PurchaseInvoices"),
            ("accounts", "Accounts"),
            ("products", "Products"),
            ("vendors", "Vendors"),
            ("customers", "Customers"),
            ("bankimports", "BankImports"),
            ("bankstatements", "BankStatements"),
            ("offerings", "Offerings"),
            ("purchaseinvoicescans", "PurchaseInvoiceScans"),
        ]

        filename_map = {
            "salesinvoices": "sales_invoices",
            "salesinvoicelines": "sales_invoice_lines",
            "purchaseinvoices": "purchase_invoices",
            "bankimports": "bank_imports",
            "bankstatements": "bank_statements",
            "purchaseinvoicescans": "purchase_invoice_scans",
        }

        items_exported = job["items_exported"]
        admin_index = {"id": admin_id, "name": admin_name, "files": {}}

        # Endpoints that support Date filtering
        date_filterable = {
            "salesinvoices", "purchaseinvoices", "bankimports",
            "bankstatements", "offerings", "purchaseinvoicescans",
        }

        def _build_date_filter(yrs):
            """Build OData $filter for a set of years."""
            if not yrs:
                return None
            min_year = min(yrs)
            max_year = max(yrs)
            return (
                f"Date ge {min_year}-01-01T00:00:00+00:00 "
                f"and Date lt {max_year + 1}-01-01T00:00:00+00:00"
            )

        # --- Phase 1: Fetch related data endpoints ---
        for key, api_endpoint in data_endpoints:
            if key not in endpoints:
                continue
            if key in completed_steps:
                continue
            if _is_cancelled(r, job_id):
                return

            _update_job(job_id, current_step=key)
            _update_step(job_id, key, status="running",
                         started_at=datetime.utcnow().isoformat())
            _publish(r, job_id, {"event": "step_start", "step": key})

            try:
                params = {}
                if years and key in date_filterable:
                    date_filter = _build_date_filter(years)
                    if date_filter:
                        params["$filter"] = date_filter

                data = client.get_paginated(
                    f"{admin_id}/{api_endpoint}", params=params, verbose=False
                )
                if not isinstance(data, list):
                    data = []

                fname = filename_map.get(key, key)
                _atomic_write_json(admin_dir / f"{fname}.json", {
                    "type": key,
                    "count": len(data),
                    "exported_at": datetime.utcnow().isoformat(),
                    "data": data,
                })

                items_exported += len(data)
                completed_steps.append(key)

                admin_index["files"][key] = {
                    "filename": f"{fname}.json",
                    "count": len(data),
                }

                _update_job(
                    job_id,
                    completed_steps=json.dumps(completed_steps),
                    items_exported=items_exported,
                )
                _update_step(job_id, key, status="completed",
                             items_count=len(data),
                             completed_at=datetime.utcnow().isoformat())
                _publish(r, job_id, {
                    "event": "step_complete", "step": key,
                    "count": len(data), "items_exported": items_exported,
                })
            except Exception as e:
                _update_step(job_id, key, status="failed",
                             error_message=str(e))
                _publish(r, job_id, {
                    "event": "step_error", "step": key, "error": str(e),
                })
                raise

        # --- Phase 2: Enrich purchase invoices with detail ---
        detail_key = "purchaseinvoices_detail"
        if detail_key in endpoints or (
            "purchaseinvoices" in endpoints and detail_key not in completed_steps
        ):
            if not _is_cancelled(r, job_id):
                _run_purchase_detail(
                    client, admin_id, admin_dir, job_id, r,
                    completed_steps, items_exported,
                )

        # --- Phase 3: Enrich sales invoices with detail + lines ---
        detail_key = "salesinvoices_detail"
        if detail_key in endpoints or (
            "salesinvoices" in endpoints and detail_key not in completed_steps
        ):
            if not _is_cancelled(r, job_id):
                items_exported = _run_sales_detail(
                    client, admin_id, admin_dir, job_id, r,
                    completed_steps, items_exported, admin_index,
                )

        # --- Phase 4: Download files ---
        file_endpoints = {"purchase_scans", "sales_pdfs", "offering_pdfs"}
        requested_files = [ep for ep in endpoints if ep in file_endpoints]
        if requested_files and not _is_cancelled(r, job_id):
            _run_file_downloads(
                client, admin_id, data_dir, job_id, r,
                completed_steps, requested_files,
            )

        # --- Phase 5: Export files (audit files, trial balances) ---
        if "export_files" in endpoints and "export_files" not in completed_steps:
            if not _is_cancelled(r, job_id):
                _run_export_files(
                    client, admin_id, admin_dir, job_id, r,
                    completed_steps, years,
                )

        # Save final index
        _atomic_write_json(admin_dir / "index.json", admin_index)
        _atomic_write_json(data_dir / "index.json", {
            "exported_at": datetime.utcnow().isoformat(),
            "administrations": [{"id": admin_id, "name": admin_name}],
        })

        # Mark complete
        now = datetime.utcnow().isoformat()
        _update_job(
            job_id, status="completed", completed_at=now,
            current_step=None, items_exported=items_exported,
            completed_steps=json.dumps(completed_steps),
        )
        _publish(r, job_id, {"status": "completed", "completed_at": now})

    except Exception as e:
        tb = traceback.format_exc()
        _update_job(
            job_id, status="failed",
            error_message=str(e), error_traceback=tb,
            current_step=None,
        )
        _publish(r, job_id, {"status": "failed", "error": str(e)})


def _run_purchase_detail(client, admin_id, admin_dir, job_id, r,
                         completed_steps, items_exported):
    """Enrich purchase invoices with full detail data."""
    pi_file = admin_dir / "purchase_invoices.json"
    if not pi_file.exists():
        return

    with open(pi_file) as f:
        pi_data = json.load(f)
    invoices = pi_data.get("data", [])
    if not invoices:
        return

    step_name = "purchaseinvoices_detail"
    _update_step(job_id, step_name, status="running",
                 items_total=len(invoices),
                 started_at=datetime.utcnow().isoformat())
    _publish(r, job_id, {
        "event": "step_start", "step": step_name, "total": len(invoices),
    })

    detailed = []
    for idx, inv in enumerate(invoices, 1):
        if _is_cancelled(r, job_id):
            return
        inv_id = inv.get("id")
        if inv_id:
            try:
                detail = client.get_json(f"{admin_id}/PurchaseInvoices/{inv_id}")
                detailed.append(detail if isinstance(detail, dict) else inv)
            except Exception:
                detailed.append(inv)
        else:
            detailed.append(inv)

        if idx % 50 == 0 or idx == len(invoices):
            _update_step(job_id, step_name, items_count=idx)
            _publish(r, job_id, {
                "event": "step_progress", "step": step_name,
                "processed": idx, "total": len(invoices),
            })
            # Atomic write of progress
            pi_data["data"] = detailed + invoices[idx:]
            _atomic_write_json(pi_file, pi_data)

    pi_data["data"] = detailed
    _atomic_write_json(pi_file, pi_data)

    completed_steps.append(step_name)
    _update_step(job_id, step_name, status="completed",
                 items_count=len(detailed),
                 completed_at=datetime.utcnow().isoformat())
    _update_job(job_id, completed_steps=json.dumps(completed_steps))
    _publish(r, job_id, {"event": "step_complete", "step": step_name})


def _run_sales_detail(client, admin_id, admin_dir, job_id, r,
                      completed_steps, items_exported, admin_index):
    """Enrich sales invoices with full detail + line items."""
    si_file = admin_dir / "sales_invoices.json"
    if not si_file.exists():
        return items_exported

    with open(si_file) as f:
        si_data = json.load(f)
    invoices = si_data.get("data", [])
    if not invoices:
        return items_exported

    step_name = "salesinvoices_detail"
    _update_step(job_id, step_name, status="running",
                 items_total=len(invoices),
                 started_at=datetime.utcnow().isoformat())
    _publish(r, job_id, {
        "event": "step_start", "step": step_name, "total": len(invoices),
    })

    detailed = []
    all_lines = []

    for idx, inv in enumerate(invoices, 1):
        if _is_cancelled(r, job_id):
            return items_exported
        inv_id = inv.get("id")
        if inv_id:
            try:
                detail = client.get_json(f"{admin_id}/SalesInvoices/{inv_id}")
                detailed.append(detail if isinstance(detail, dict) else inv)
            except Exception:
                detailed.append(inv)

            try:
                lines = client.get_paginated(
                    f"{admin_id}/SalesInvoices/{inv_id}/Lines", verbose=False
                )
                for line in lines:
                    line["InvoiceId"] = inv_id
                    line["InvoiceReference"] = inv.get("InvoiceReference") or inv.get("Reference")
                    line["InvoiceNumber"] = inv.get("InvoiceNumber")
                    line["InvoiceDate"] = inv.get("Date")
                    all_lines.append(line)
            except Exception:
                pass
        else:
            detailed.append(inv)

        if idx % 50 == 0 or idx == len(invoices):
            _update_step(job_id, step_name, items_count=idx)
            _publish(r, job_id, {
                "event": "step_progress", "step": step_name,
                "processed": idx, "total": len(invoices),
            })

    si_data["data"] = detailed
    _atomic_write_json(si_file, si_data)

    if all_lines:
        _atomic_write_json(admin_dir / "sales_invoice_lines.json", {
            "type": "salesinvoicelines",
            "count": len(all_lines),
            "exported_at": datetime.utcnow().isoformat(),
            "data": all_lines,
        })
        admin_index["files"]["salesinvoicelines"] = {
            "filename": "sales_invoice_lines.json",
            "count": len(all_lines),
        }
        items_exported += len(all_lines)

    completed_steps.append(step_name)
    _update_step(job_id, step_name, status="completed",
                 items_count=len(detailed),
                 completed_at=datetime.utcnow().isoformat())
    _update_job(job_id, completed_steps=json.dumps(completed_steps),
                items_exported=items_exported)
    _publish(r, job_id, {"event": "step_complete", "step": step_name})
    return items_exported


def _run_file_downloads(client, admin_id, data_dir, job_id, r,
                        completed_steps, requested_files):
    """Download binary files (scans, PDFs)."""
    from reeleezee_exporter.download_files import ReeleezeeFileDownloader

    downloader = ReeleezeeFileDownloader(client)
    files_dir = data_dir / "files"
    files_dir.mkdir(exist_ok=True)

    for file_type in requested_files:
        if file_type in completed_steps:
            continue
        if _is_cancelled(r, job_id):
            return

        _update_step(job_id, file_type, status="running",
                     started_at=datetime.utcnow().isoformat())
        _publish(r, job_id, {"event": "step_start", "step": file_type})

        try:
            stats = {"total_bytes": 0}
            if file_type == "purchase_scans":
                downloader._download_purchase_scans(files_dir, stats)
            elif file_type == "sales_pdfs":
                downloader._download_sales_invoices(files_dir, stats)
            elif file_type == "offering_pdfs":
                downloader._download_offerings(files_dir, stats)

            completed_steps.append(file_type)
            _update_step(job_id, file_type, status="completed",
                         completed_at=datetime.utcnow().isoformat())
            _update_job(job_id, completed_steps=json.dumps(completed_steps))
            _publish(r, job_id, {"event": "step_complete", "step": file_type})
        except Exception as e:
            _update_step(job_id, file_type, status="failed",
                         error_message=str(e))
            _publish(r, job_id, {
                "event": "step_error", "step": file_type, "error": str(e),
            })
            raise


def _run_export_files(client, admin_id, admin_dir, job_id, r,
                      completed_steps, selected_years=None):
    """Download administration export files (audit files, etc.)."""
    import base64

    step_name = "export_files"
    _update_step(job_id, step_name, status="running",
                 started_at=datetime.utcnow().isoformat())
    _publish(r, job_id, {"event": "step_start", "step": step_name})

    try:
        exports = client.get_json(f"{admin_id}/AdministrationExports")
        if isinstance(exports, dict) and "value" in exports:
            exports = exports["value"]
        if not isinstance(exports, list):
            exports = []

        from reeleezee_exporter.export_data import ReeleezeeExporter
        exporter = ReeleezeeExporter(client)
        export_years = selected_years if selected_years else exporter.get_available_years()

        export_files = {}
        downloaded = 0

        for export in exports:
            export_id = export.get("id") or export.get("Id")
            export_type = export.get("Type") or export.get("type")
            if not export_id:
                continue
            for year in export_years:
                if _is_cancelled(r, job_id):
                    return
                try:
                    resp = client.get(
                        f"{admin_id}/AdministrationExports/{export_id}/Download",
                        params={"selectedYear": year}, timeout=60, accept="*/*",
                    )
                    if resp.status_code == 200 and len(resp.content) > 0:
                        export_files[f"{export_id}_{year}"] = {
                            "data": base64.b64encode(resp.content).decode("utf-8"),
                            "size_bytes": len(resp.content),
                            "type": export_type,
                            "year": year,
                        }
                        downloaded += 1
                except Exception:
                    continue

        _atomic_write_json(admin_dir / "export_files.json", {
            "type": "export_files",
            "count": len(export_files),
            "exported_at": datetime.utcnow().isoformat(),
            "data": export_files,
        })

        completed_steps.append(step_name)
        _update_step(job_id, step_name, status="completed",
                     items_count=downloaded,
                     completed_at=datetime.utcnow().isoformat())
        _update_job(job_id, completed_steps=json.dumps(completed_steps))
        _publish(r, job_id, {
            "event": "step_complete", "step": step_name, "count": downloaded,
        })
    except Exception as e:
        _update_step(job_id, step_name, status="failed",
                     error_message=str(e))
        raise
