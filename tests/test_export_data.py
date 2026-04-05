"""Tests for the data export module."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


class TestReeleezeeExporter:
    """Tests for ReeleezeeExporter save methods."""

    def _make_mock_client(self):
        """Create a mock client with test administrations."""
        client = MagicMock()
        client.administrations = [{"id": "test-id", "Name": "Test Admin"}]
        return client

    def test_save_structured_creates_correct_directory_structure(self):
        """Verify that save_structured creates the expected files and directories."""
        from reeleezee_exporter.export_data import ReeleezeeExporter

        client = self._make_mock_client()
        exporter = ReeleezeeExporter(client)

        data = {
            "export_metadata": {
                "exported_at": "2025-01-01T00:00:00",
                "total_administrations": 1,
                "api_version": "v1",
            },
            "administrations": [
                {
                    "id": "test-admin-id",
                    "name": "Test Admin",
                    "administration": {"Name": "Test Admin", "id": "test-admin-id"},
                    "exports": [],
                    "export_files": {},
                    "related_data": {
                        "salesinvoices": [
                            {"id": "inv-1", "InvoiceNumber": "001", "Date": "2025-01-15"},
                            {"id": "inv-2", "InvoiceNumber": "002", "Date": "2025-02-20"},
                        ],
                        "customers": [
                            {"id": "cust-1", "Name": "Customer A"},
                        ],
                    },
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.save_structured(data, tmpdir)

            # Check main index
            main_index_path = os.path.join(tmpdir, "index.json")
            assert os.path.exists(main_index_path)
            with open(main_index_path) as f:
                main_index = json.load(f)
            assert len(main_index["administrations"]) == 1
            assert main_index["administrations"][0]["id"] == "test-admin-id"

            # Check admin directory
            admin_dir = os.path.join(tmpdir, "test-admin-id")
            assert os.path.isdir(admin_dir)

            # Check admin index
            admin_index_path = os.path.join(admin_dir, "index.json")
            assert os.path.exists(admin_index_path)

            # Check data files
            assert os.path.exists(os.path.join(admin_dir, "sales_invoices.json"))
            assert os.path.exists(os.path.join(admin_dir, "customers.json"))
            assert os.path.exists(os.path.join(admin_dir, "administration.json"))

            # Verify content
            with open(os.path.join(admin_dir, "sales_invoices.json")) as f:
                si_data = json.load(f)
            assert si_data["count"] == 2
            assert si_data["type"] == "salesinvoices"

    def test_save_json_creates_single_file(self):
        """Verify that save_json creates a single valid JSON file."""
        from reeleezee_exporter.export_data import ReeleezeeExporter

        client = self._make_mock_client()
        exporter = ReeleezeeExporter(client)

        data = {
            "export_metadata": {"exported_at": "2025-01-01T00:00:00"},
            "administrations": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "export.json")
            exporter.save_json(data, path)

            assert os.path.exists(path)
            with open(path) as f:
                loaded = json.load(f)
            assert loaded["export_metadata"]["exported_at"] == "2025-01-01T00:00:00"

    def test_get_available_years_range(self):
        """Verify that year range is calculated correctly."""
        from reeleezee_exporter.export_data import ReeleezeeExporter

        client = self._make_mock_client()
        exporter = ReeleezeeExporter(client)

        years = exporter.get_available_years(start_year=2020)
        assert years[0] == 2020
        assert len(years) > 1
        # Should include current year
        from datetime import datetime
        assert datetime.now().year in years
