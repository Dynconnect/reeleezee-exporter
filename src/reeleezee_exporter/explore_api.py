#!/usr/bin/env python3
"""
Reeleezee API Explorer.

Interactive tool to discover and probe Reeleezee API endpoints.
Useful for understanding the API structure and finding new endpoints.

Usage:
    reeleezee-explore --username USER --password PASS
    reeleezee-explore  # reads credentials from .env file
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import urljoin

from .client import ReeleezeeClient


def _load_env():
    """Load environment variables from .env file if available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def probe_endpoint(client: ReeleezeeClient, endpoint: str,
                   accept: str = "application/json", desc: str = ""):
    """Probe an API endpoint and report what it returns.

    Args:
        client: Authenticated API client.
        endpoint: API endpoint path.
        accept: Accept header value.
        desc: Human-readable description.

    Returns:
        Dict with probe results.
    """
    try:
        r = client.get(endpoint, accept=accept, timeout=15)
        content_type = r.headers.get("Content-Type", "unknown")
        size = len(r.content)

        status_icon = "OK" if r.status_code == 200 else "FAIL"
        print(f"  [{status_icon}] [{r.status_code}] {endpoint}")
        print(f"    Content-Type: {content_type}, Size: {size} bytes")

        if r.status_code == 200 and "json" in content_type:
            try:
                data = r.json()
                if isinstance(data, dict):
                    keys = list(data.keys())[:10]
                    print(f"    Keys: {keys}")
                    if "value" in data and isinstance(data["value"], list):
                        print(f"    Items: {len(data['value'])}")
                elif isinstance(data, list):
                    print(f"    List with {len(data)} items")
            except Exception:
                pass
        elif r.status_code == 200:
            if "pdf" in content_type or "image" in content_type:
                print(f"    Binary content (likely a document file)")

        return {"status": r.status_code, "content_type": content_type, "size": size}

    except Exception as e:
        print(f"  [ERROR] {endpoint}: {e}")
        return {"status": "error", "error": str(e)}


def explore_metadata(client: ReeleezeeClient, admin_id: str):
    """Fetch and analyze the OData metadata to discover all entity types.

    Args:
        client: Authenticated API client.
        admin_id: Administration ID.
    """
    print("\n" + "=" * 70)
    print("OData Metadata")
    print("=" * 70)

    for ep in ["$metadata", f"{admin_id}/$metadata"]:
        r = client.get(ep, accept="application/xml,text/xml,*/*", timeout=15)
        print(f"  [{r.status_code}] {ep} ({len(r.content)} bytes)")

        if r.status_code == 200:
            text = r.text
            entity_types = re.findall(r'EntityType\s+Name="([^"]+)"', text)
            entity_sets = re.findall(r'EntitySet\s+Name="([^"]+)"', text)

            print(f"    Entity types: {len(entity_types)}")
            print(f"    Entity sets (API endpoints): {len(entity_sets)}")

            if entity_sets:
                print(f"\n    All endpoints:")
                for es in sorted(entity_sets):
                    print(f"      - {es}")


def explore_all(client: ReeleezeeClient):
    """Run full API exploration.

    Args:
        client: Authenticated API client.
    """
    admin_id = client.administrations[0]["id"]
    admin_name = client.administrations[0].get("Name", "unknown")

    print(f"\nAdministration: {admin_name} ({admin_id})")

    # Explore metadata first
    explore_metadata(client, admin_id)

    # Probe known endpoints
    print("\n" + "=" * 70)
    print("Known Endpoints")
    print("=" * 70)

    endpoints = [
        (f"{admin_id}/SalesInvoices?$top=1", "Sales Invoices"),
        (f"{admin_id}/PurchaseInvoices?$top=1", "Purchase Invoices"),
        (f"{admin_id}/Customers?$top=1", "Customers"),
        (f"{admin_id}/Vendors?$top=1", "Vendors"),
        (f"{admin_id}/Products?$top=1", "Products"),
        (f"{admin_id}/Relations?$top=1", "Relations"),
        (f"{admin_id}/Addresses?$top=1", "Addresses"),
        (f"{admin_id}/Documents?$top=1", "Documents"),
        (f"{admin_id}/Accounts?$top=1", "Accounts"),
        (f"{admin_id}/BankImports?$top=1", "Bank Imports"),
        (f"{admin_id}/BankStatements?$top=1", "Bank Statements"),
        (f"{admin_id}/Offerings?$top=1", "Offerings"),
        (f"{admin_id}/PurchaseInvoiceScans?$top=1", "Purchase Invoice Scans"),
        (f"{admin_id}/AdministrationExports", "Administration Exports"),
        ("AdministrationExportInfoTypes", "Export Info Types"),
    ]

    for ep, desc in endpoints:
        probe_endpoint(client, ep, desc=desc)

    # Probe document-related endpoints
    print("\n" + "=" * 70)
    print("Document/File Endpoints")
    print("=" * 70)

    file_endpoints = [
        (f"{admin_id}/Files?$top=1", "Files"),
        (f"{admin_id}/Media", "Media"),
        (f"{admin_id}/Blobs", "Blobs"),
    ]

    for ep, desc in file_endpoints:
        probe_endpoint(client, ep, accept="*/*", desc=desc)


def main():
    """CLI entry point for API exploration."""
    _load_env()

    parser = argparse.ArgumentParser(
        description="Explore Reeleezee API endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --username USER --password PASS
  %(prog)s  # reads REELEEZEE_USERNAME and REELEEZEE_PASSWORD from .env
        """,
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("REELEEZEE_USERNAME"),
        help="Reeleezee username (or set REELEEZEE_USERNAME env var)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("REELEEZEE_PASSWORD"),
        help="Reeleezee password (or set REELEEZEE_PASSWORD env var)",
    )

    args = parser.parse_args()

    if not args.username or not args.password:
        print("Error: credentials required.")
        print("Provide --username and --password, or set REELEEZEE_USERNAME")
        print("and REELEEZEE_PASSWORD environment variables (or in a .env file).")
        sys.exit(1)

    print("=" * 70)
    print("Reeleezee API Explorer")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    from .client import AuthenticationError
    try:
        client = ReeleezeeClient(args.username, args.password)
    except AuthenticationError as e:
        print(f"Error: {e}")
        import sys
        sys.exit(1)
    explore_all(client)

    print("\n" + "=" * 70)
    print("Exploration complete!")
    print(f"Finished: {datetime.now().isoformat()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
