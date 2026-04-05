#!/usr/bin/env python3
"""
Reeleezee Full Administration Data Export.

Exports all structured data from Reeleezee as JSON files:
- Administration details
- Sales invoices (with line items)
- Purchase invoices (with full details)
- Customers, vendors, products
- Bank imports and statements
- Administration export files (audit files, trial balances, etc.)

Usage:
    reeleezee-export --username USER --password PASS
    reeleezee-export --username USER --password PASS --output-dir ./my_exports
    reeleezee-export  # reads credentials from .env file
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .client import ReeleezeeClient


def _load_env():
    """Load environment variables from .env file if available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _timestamp():
    """Return current time formatted for log output."""
    return datetime.now().strftime("%H:%M:%S")


def _log(message: str):
    """Print a timestamped log message."""
    print(f"[{_timestamp()}] {message}", flush=True)


class ReeleezeeExporter:
    """Exports all administration data from Reeleezee to structured JSON files.

    Connects to the Reeleezee API, discovers all administrations, and exports
    their complete data including invoices, relations, products, bank data,
    and administration export files (audit files, trial balances, etc.).
    """

    # API endpoints to export, mapped to human-readable names
    RELATED_ENDPOINTS = [
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

    def __init__(self, client: ReeleezeeClient):
        """Initialize with an authenticated API client.

        Args:
            client: An authenticated ReeleezeeClient instance.
        """
        self.client = client

    def get_available_years(self, start_year: int = 2014) -> List[int]:
        """Return list of years to export (from start_year through current year + 1)."""
        current_year = datetime.now().year
        return list(range(start_year, current_year + 2))

    def _get_year_from_date(self, date_str: str) -> Optional[int]:
        """Extract year from an ISO date string."""
        if not date_str:
            return None
        try:
            return int(date_str[:4])
        except (ValueError, IndexError):
            return None

    def export_administration(self, admin_id: str, admin_name: str) -> Dict:
        """Export all data for a single administration.

        Args:
            admin_id: The administration UUID.
            admin_name: Human-readable administration name.

        Returns:
            Dict containing all exported data for this administration.
        """
        _log(f"Exporting administration: {admin_name} ({admin_id})")

        admin_data = {
            "id": admin_id,
            "name": admin_name,
            "exported_at": datetime.now().isoformat(),
            "administration": {},
            "exports": [],
            "export_files": {},
            "related_data": {},
        }

        # 1. Get administration details
        _log("  Fetching administration details...")
        try:
            admin_info = self.client.get_json(f"Administrations/{admin_id}")
            admin_data["administration"] = admin_info if isinstance(admin_info, dict) else {}
            _log(f"  Administration details: {len(admin_data['administration'])} fields")
        except Exception as e:
            _log(f"  Warning: Could not fetch administration details: {e}")

        # 2. Get and download export files (audit files, trial balances, etc.)
        _log("  Fetching available administration exports...")
        try:
            exports_raw = self.client.get_json(f"{admin_id}/AdministrationExports")
            if isinstance(exports_raw, dict) and "value" in exports_raw:
                exports = exports_raw["value"]
            elif isinstance(exports_raw, list):
                exports = exports_raw
            else:
                exports = []

            admin_data["exports"] = exports
            _log(f"  Found {len(exports)} export types")

            if exports:
                years = self.get_available_years()
                _log(f"  Downloading export files for years {years[0]}-{years[-1]}...")
                downloaded = 0
                total_size = 0

                for export in exports:
                    export_id = export.get("id") or export.get("Id")
                    export_type = export.get("Type") or export.get("type")
                    if not export_id:
                        continue

                    for year in years:
                        try:
                            endpoint = f"{admin_id}/AdministrationExports/{export_id}/Download"
                            r = self.client.get(endpoint, params={"selectedYear": year},
                                                timeout=60, accept="*/*")
                            if r.status_code == 200 and len(r.content) > 0:
                                admin_data["export_files"][f"{export_id}_{year}"] = {
                                    "data": base64.b64encode(r.content).decode("utf-8"),
                                    "size_bytes": len(r.content),
                                    "type": export_type,
                                    "year": year,
                                }
                                downloaded += 1
                                total_size += len(r.content)
                        except Exception:
                            continue

                total_mb = total_size / (1024 * 1024)
                _log(f"  Downloaded {downloaded} export files ({total_mb:.1f} MB)")

        except Exception as e:
            _log(f"  Warning: Could not fetch exports: {e}")

        # 3. Fetch all related data
        _log(f"  Fetching related data ({len(self.RELATED_ENDPOINTS)} endpoints)...")
        total_items = 0

        for idx, (key, endpoint_name) in enumerate(self.RELATED_ENDPOINTS, 1):
            try:
                _log(f"    [{idx}/{len(self.RELATED_ENDPOINTS)}] Fetching {key}...")
                data = self.client.get_paginated(
                    f"{admin_id}/{endpoint_name}", verbose=False
                )
                if isinstance(data, list):
                    admin_data["related_data"][key] = data
                    total_items += len(data)
                    _log(f"    {key}: {len(data)} items")
            except Exception as e:
                _log(f"    Warning: Could not fetch {key}: {e}")

        # 4. Fetch detailed purchase invoice data
        purchase_invoices = admin_data["related_data"].get("purchaseinvoices", [])
        if purchase_invoices:
            _log(f"  Fetching detailed data for {len(purchase_invoices)} purchase invoices...")
            detailed = []
            for idx, inv in enumerate(purchase_invoices, 1):
                inv_id = inv.get("id")
                if inv_id:
                    try:
                        detail = self.client.get_json(
                            f"{admin_id}/PurchaseInvoices/{inv_id}"
                        )
                        detailed.append(detail if isinstance(detail, dict) else inv)
                    except Exception:
                        detailed.append(inv)
                if idx % 100 == 0:
                    _log(f"    Processed {idx}/{len(purchase_invoices)} purchase invoices")
            admin_data["related_data"]["purchaseinvoices"] = detailed

        # 5. Fetch detailed sales invoice data with line items
        sales_invoices = admin_data["related_data"].get("salesinvoices", [])
        if sales_invoices:
            _log(f"  Fetching detailed data and line items for {len(sales_invoices)} sales invoices...")
            detailed_invoices = []
            all_lines = []

            for idx, inv in enumerate(sales_invoices, 1):
                inv_id = inv.get("id")
                if inv_id:
                    # Fetch full invoice detail
                    try:
                        detail = self.client.get_json(
                            f"{admin_id}/SalesInvoices/{inv_id}"
                        )
                        detailed_invoices.append(detail if isinstance(detail, dict) else inv)
                    except Exception:
                        detailed_invoices.append(inv)

                    # Fetch line items
                    try:
                        lines = self.client.get_paginated(
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

                if idx % 50 == 0:
                    _log(f"    Processed {idx}/{len(sales_invoices)} sales invoices")

            admin_data["related_data"]["salesinvoices"] = detailed_invoices
            admin_data["related_data"]["salesinvoicelines"] = all_lines
            total_items += len(all_lines)
            _log(f"    salesinvoicelines: {len(all_lines)} line items")

        _log(f"  Total related items: {total_items}")
        _log(f"  Export complete for {admin_name}")
        return admin_data

    def export_all(self) -> Dict:
        """Export all administrations.

        Returns:
            Dict containing all exported data with metadata.
        """
        _log("=" * 60)
        _log("Starting Reeleezee data export")
        _log("=" * 60)

        start_time = time.time()
        admins = self.client.administrations
        _log(f"Found {len(admins)} administration(s)")

        result = {
            "export_metadata": {
                "exported_at": datetime.now().isoformat(),
                "total_administrations": len(admins),
                "api_version": "v1",
            },
            "administrations": [],
        }

        for idx, admin in enumerate(admins, 1):
            admin_id = admin.get("id") or admin.get("Id")
            admin_name = admin.get("name") or admin.get("Name") or admin_id
            _log(f"\n[{idx}/{len(admins)}] {admin_name}")
            admin_data = self.export_administration(admin_id, admin_name)
            result["administrations"].append(admin_data)

        elapsed = time.time() - start_time
        _log("=" * 60)
        _log(f"Export completed in {elapsed:.0f} seconds")
        _log(f"Total administrations: {len(admins)}")
        _log("=" * 60)

        return result

    def save_structured(self, data: Dict, output_dir: str):
        """Save exported data as structured JSON files organized by administration and year.

        Creates a directory structure:
            output_dir/
                index.json
                {admin_id}/
                    index.json
                    administration.json
                    sales_invoices.json
                    purchase_invoices.json
                    ...

        Args:
            data: The complete exported data dict.
            output_dir: Target directory path.
        """
        _log(f"Saving structured JSON to {output_dir}...")
        start_time = time.time()
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        main_index = {
            "export_metadata": data.get("export_metadata", {}),
            "exported_at": datetime.now().isoformat(),
            "administrations": [],
        }

        for admin_data in data.get("administrations", []):
            admin_id = admin_data.get("id", "unknown")
            admin_info = admin_data.get("administration", {})
            admin_name = (admin_info.get("name") or admin_info.get("Name")
                          or admin_data.get("name") or admin_id)

            admin_dir = output_path / admin_id
            admin_dir.mkdir(exist_ok=True)

            admin_index = {
                "id": admin_id,
                "name": admin_name,
                "exported_at": datetime.now().isoformat(),
                "files": {},
            }

            # Save administration details
            admin_file = admin_dir / "administration.json"
            with open(admin_file, "w", encoding="utf-8") as f:
                json.dump(admin_info, f, indent=2, ensure_ascii=False)

            # Save each related data type
            related = admin_data.get("related_data", {})
            total_items = 0

            data_type_filenames = {
                "salesinvoices": "sales_invoices.json",
                "salesinvoicelines": "sales_invoice_lines.json",
                "purchaseinvoices": "purchase_invoices.json",
                "vendors": "vendors.json",
                "customers": "customers.json",
                "products": "products.json",
                "relations": "relations.json",
                "addresses": "addresses.json",
                "documents": "documents.json",
                "accounts": "accounts.json",
                "bankimports": "bank_imports.json",
                "bankstatements": "bank_statements.json",
                "offerings": "offerings.json",
                "purchaseinvoicescans": "purchase_invoice_scans.json",
            }

            for key, filename in data_type_filenames.items():
                items = related.get(key, [])
                if items:
                    filepath = admin_dir / filename
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump({
                            "type": key,
                            "count": len(items),
                            "exported_at": datetime.now().isoformat(),
                            "data": items,
                        }, f, indent=2, ensure_ascii=False)

                    file_size_kb = os.path.getsize(filepath) / 1024
                    admin_index["files"][key] = {
                        "filename": filename,
                        "count": len(items),
                        "size_kb": round(file_size_kb, 2),
                    }
                    total_items += len(items)

            # Save exports metadata
            exports = admin_data.get("exports", [])
            if exports:
                exports_file = admin_dir / "exports.json"
                with open(exports_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "type": "exports",
                        "count": len(exports),
                        "exported_at": datetime.now().isoformat(),
                        "data": exports,
                    }, f, indent=2, ensure_ascii=False)
                admin_index["files"]["exports"] = {
                    "filename": "exports.json",
                    "count": len(exports),
                    "size_kb": round(os.path.getsize(exports_file) / 1024, 2),
                }

            # Save export files (base64-encoded audit files, trial balances, etc.)
            export_files = admin_data.get("export_files", {})
            if export_files:
                ef_file = admin_dir / "export_files.json"
                with open(ef_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "type": "export_files",
                        "count": len(export_files),
                        "exported_at": datetime.now().isoformat(),
                        "data": export_files,
                    }, f, indent=2, ensure_ascii=False)
                admin_index["files"]["export_files"] = {
                    "filename": "export_files.json",
                    "count": len(export_files),
                    "size_kb": round(os.path.getsize(ef_file) / 1024, 2),
                }

            # Save admin index
            with open(admin_dir / "index.json", "w", encoding="utf-8") as f:
                json.dump(admin_index, f, indent=2, ensure_ascii=False)

            main_index["administrations"].append({
                "id": admin_id,
                "name": admin_name,
                "directory": admin_id,
                "index_file": f"{admin_id}/index.json",
                "file_count": len(admin_index["files"]),
                "total_items": total_items,
            })

        # Save main index
        with open(output_path / "index.json", "w", encoding="utf-8") as f:
            json.dump(main_index, f, indent=2, ensure_ascii=False)

        elapsed = time.time() - start_time
        total_size = sum(
            f.stat().st_size for f in output_path.rglob("*.json")
        ) / (1024 * 1024)
        _log(f"Structured JSON saved: {total_size:.1f} MB in {elapsed:.1f}s")
        _log(f"Output directory: {output_path}")

    def save_json(self, data: Dict, output_path: str):
        """Save all exported data as a single JSON file.

        Args:
            data: The complete exported data dict.
            output_path: Target file path.
        """
        _log(f"Saving JSON to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        _log(f"JSON saved: {size_mb:.1f} MB")


def main():
    """CLI entry point for data export."""
    _load_env()

    parser = argparse.ArgumentParser(
        description="Export all data from Reeleezee accounting platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --username USER --password PASS
  %(prog)s --username USER --password PASS --output-dir ./my_exports
  %(prog)s --format json  # single JSON file instead of structured
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
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: exports/reeleezee_export_TIMESTAMP)",
    )
    parser.add_argument(
        "--format",
        choices=["structured", "json", "both"],
        default="structured",
        help="Output format (default: structured)",
    )

    args = parser.parse_args()

    if not args.username or not args.password:
        print("Error: credentials required.")
        print("Provide --username and --password, or set REELEEZEE_USERNAME")
        print("and REELEEZEE_PASSWORD environment variables (or in a .env file).")
        sys.exit(1)

    # Default output directory
    if not args.output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output_dir = f"exports/reeleezee_export_{timestamp}"

    # Connect and export
    from .client import AuthenticationError
    try:
        client = ReeleezeeClient(args.username, args.password)
    except AuthenticationError as e:
        print(f"Error: {e}")
        sys.exit(1)
    exporter = ReeleezeeExporter(client)
    data = exporter.export_all()

    # Save
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.format in ("structured", "both"):
        exporter.save_structured(data, str(output_dir))

    if args.format in ("json", "both"):
        json_path = str(output_dir / "reeleezee_export.json")
        exporter.save_json(data, json_path)

    _log("")
    _log("Export completed successfully!")
    _log(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
