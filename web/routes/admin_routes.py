"""Administration metadata routes: years, export types."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..auth import decrypt_credentials, get_current_session

router = APIRouter(tags=["admin"])


@router.get("/administrations/{admin_id}/years")
def get_years_quick(admin_id: str, session: dict = Depends(get_current_session)):
    """Quick year list derived from Administration.CreateDate to current year.

    Returns immediately. The frontend should follow up with the /years/detailed
    endpoint to get actual item counts per year.
    """
    admins = session.get("administrations", "[]")
    if isinstance(admins, str):
        admins = json.loads(admins)

    admin = None
    for a in admins:
        if (a.get("id") or a.get("Id")) == admin_id:
            admin = a
            break
    if not admin:
        raise HTTPException(status_code=404, detail="Administration not found")

    create_date = admin.get("CreateDate", "")
    try:
        start_year = int(create_date[:4])
    except (ValueError, IndexError):
        start_year = 2014

    current_year = datetime.now().year
    years = []
    for y in range(start_year, current_year + 1):
        years.append({"year": y, "has_data": True, "counts": None})

    return {
        "admin_id": admin_id,
        "method": "quick",
        "start_year": start_year,
        "years": years,
    }


@router.get("/administrations/{admin_id}/years/detailed")
def get_years_detailed(admin_id: str, session: dict = Depends(get_current_session)):
    """Probe each year to get actual item counts from the API.

    This is slower (makes API calls per year) but gives accurate data.
    """
    from reeleezee_exporter.client import ReeleezeeClient, AuthenticationError

    creds = decrypt_credentials(session["encrypted_credentials"])
    try:
        client = ReeleezeeClient(creds["username"], creds["password"])
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Get admin create date for year range
    admins = session.get("administrations", "[]")
    if isinstance(admins, str):
        admins = json.loads(admins)

    admin = None
    for a in admins:
        if (a.get("id") or a.get("Id")) == admin_id:
            admin = a
            break
    if not admin:
        raise HTTPException(status_code=404, detail="Administration not found")

    create_date = admin.get("CreateDate", "")
    try:
        start_year = int(create_date[:4])
    except (ValueError, IndexError):
        start_year = 2014

    current_year = datetime.now().year

    # Probe each year for sales invoices and purchase invoices
    endpoints_to_probe = [
        ("sales_invoices", "SalesInvoices"),
        ("purchase_invoices", "PurchaseInvoices"),
    ]

    years = []
    for y in range(start_year, current_year + 1):
        year_start = f"{y}-01-01T00:00:00+00:00"
        year_end = f"{y + 1}-01-01T00:00:00+00:00"

        counts = {}
        has_data = False

        for label, endpoint in endpoints_to_probe:
            try:
                filter_str = f"Date ge {year_start} and Date lt {year_end}"
                r = client.get(
                    f"{admin_id}/{endpoint}",
                    params={"$filter": filter_str, "$top": "1"},
                    timeout=10,
                )
                if r.status_code == 200:
                    data = r.json()
                    items = data.get("value", []) if isinstance(data, dict) else []
                    if items:
                        has_data = True
                        counts[label] = True
                    else:
                        counts[label] = False
                else:
                    counts[label] = None
            except Exception:
                counts[label] = None

        years.append({
            "year": y,
            "has_data": has_data,
            "counts": counts,
        })

    return {
        "admin_id": admin_id,
        "method": "detailed",
        "start_year": start_year,
        "years": years,
    }
