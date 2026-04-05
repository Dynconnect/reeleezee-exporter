"""Tests for the web layer: auth, routes, database, workers."""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_test_env(tmpdir):
    """Set web config to use a temp directory for DB and data."""
    from web import config
    config.DATABASE_PATH = os.path.join(tmpdir, "test.db")
    config.DATA_DIR = os.path.join(tmpdir, "exports")
    config.SECRET_KEY = "test-secret-key-for-unit-tests"
    os.makedirs(config.DATA_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Database tests
# ---------------------------------------------------------------------------

class TestDatabase:

    def test_init_db_creates_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_test_env(tmpdir)
            from web.database import init_db, get_db

            init_db()

            with get_db() as db:
                tables = [r[0] for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()]

            assert "sessions" in tables
            assert "jobs" in tables
            assert "job_steps" in tables

    def test_row_to_dict_parses_json_fields(self):
        from web.database import row_to_dict

        class FakeRow(dict):
            def keys(self):
                return super().keys()

        row = FakeRow({
            "id": "abc",
            "endpoints": '["a","b"]',
            "completed_steps": '[]',
            "encrypted_credentials": b"secret",
        })
        result = row_to_dict(row)

        assert result["endpoints"] == ["a", "b"]
        assert result["completed_steps"] == []
        assert "encrypted_credentials" not in result


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:

    def test_encrypt_decrypt_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_test_env(tmpdir)
            from web.auth import encrypt_credentials, decrypt_credentials

            encrypted = encrypt_credentials("testuser", "testpass")
            assert isinstance(encrypted, bytes)

            decrypted = decrypt_credentials(encrypted)
            assert decrypted["username"] == "testuser"
            assert decrypted["password"] == "testpass"

    def test_create_and_get_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_test_env(tmpdir)
            from web.database import init_db
            from web.auth import create_session, get_session, encrypt_credentials

            init_db()
            encrypted = encrypt_credentials("user", "pass")
            admins = [{"id": "admin-1", "Name": "Test"}]

            session_id = create_session(encrypted, admins)
            assert isinstance(session_id, str)
            assert len(session_id) == 36

            session = get_session(session_id)
            assert session is not None
            assert session["id"] == session_id

    def test_get_session_returns_none_for_invalid_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_test_env(tmpdir)
            from web.database import init_db
            from web.auth import get_session

            init_db()
            assert get_session("nonexistent-id") is None

    def test_delete_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_test_env(tmpdir)
            from web.database import init_db
            from web.auth import (
                create_session, get_session, delete_session, encrypt_credentials,
            )

            init_db()
            encrypted = encrypt_credentials("user", "pass")
            session_id = create_session(encrypted, [])

            delete_session(session_id)
            assert get_session(session_id) is None


# ---------------------------------------------------------------------------
# Schemas tests
# ---------------------------------------------------------------------------

class TestSchemas:

    def test_login_request_validation(self):
        from web.schemas import LoginRequest
        req = LoginRequest(username="user", password="pass")
        assert req.username == "user"

    def test_job_create_request_defaults(self):
        from web.schemas import JobCreateRequest
        req = JobCreateRequest(admin_id="abc")
        assert req.job_type == "data"
        assert req.endpoints == []
        assert req.years == []

    def test_job_create_request_with_years(self):
        from web.schemas import JobCreateRequest
        req = JobCreateRequest(
            admin_id="abc", job_type="both",
            endpoints=["customers"], years=[2023, 2024],
        )
        assert req.years == [2023, 2024]


# ---------------------------------------------------------------------------
# FastAPI route tests (using TestClient)
# ---------------------------------------------------------------------------

class TestRoutes:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        _setup_test_env(str(tmp_path))
        from web.database import init_db
        init_db()

    def _get_client(self):
        from web.app import create_app
        from fastapi.testclient import TestClient
        return TestClient(create_app())

    def test_me_returns_401_without_session(self):
        client = self._get_client()
        r = client.get("/api/me")
        assert r.status_code == 401

    def _mock_client(self):
        """Create a mock ReeleezeeClient."""
        mock = MagicMock()
        mock.administrations = [{"id": "adm-1", "Name": "Test"}]
        return mock

    @patch("web.routes.auth_routes.ReeleezeeClient")
    def test_login_success(self, mock_cls):
        mock_cls.return_value = self._mock_client()
        client = self._get_client()
        r = client.post("/api/login", json={"username": "u", "password": "p"})
        assert r.status_code == 200
        assert r.json()["message"] == "Authenticated successfully"
        assert len(r.json()["administrations"]) == 1
        assert "session_id" in r.cookies

    @patch("web.routes.auth_routes.ReeleezeeClient")
    def test_login_failure(self, mock_cls):
        from reeleezee_exporter.client import AuthenticationError
        mock_cls.side_effect = AuthenticationError("Bad credentials")
        client = self._get_client()
        r = client.post("/api/login", json={"username": "bad", "password": "bad"})
        assert r.status_code == 401

    @patch("web.routes.auth_routes.ReeleezeeClient")
    def test_me_returns_session_info(self, mock_cls):
        mc = self._mock_client()
        mc.administrations = [{"id": "adm-1", "Name": "TestAdmin"}]
        mock_cls.return_value = mc
        client = self._get_client()
        client.post("/api/login", json={"username": "u", "password": "p"})
        r = client.get("/api/me")
        assert r.status_code == 200
        assert r.json()["authenticated"] is True
        assert r.json()["administrations"][0]["Name"] == "TestAdmin"

    @patch("web.routes.auth_routes.ReeleezeeClient")
    def test_logout_clears_session(self, mock_cls):
        mock_cls.return_value = self._mock_client()
        client = self._get_client()
        client.post("/api/login", json={"username": "u", "password": "p"})
        r = client.post("/api/logout")
        assert r.status_code == 200
        r = client.get("/api/me")
        assert r.status_code == 401

    @patch("web.routes.job_routes.redis")
    @patch("web.routes.auth_routes.ReeleezeeClient")
    def test_create_job(self, mock_cls, mock_redis):
        mock_cls.return_value = self._mock_client()
        mock_redis.from_url.return_value = MagicMock()
        with patch("rq.Queue", return_value=MagicMock()):
            client = self._get_client()
            client.post("/api/login", json={"username": "u", "password": "p"})
            r = client.post("/api/jobs", json={
                "admin_id": "adm-1", "job_type": "data",
                "endpoints": ["customers", "products"], "years": [2024],
            })
            assert r.status_code == 200
            assert "id" in r.json()
            assert r.json()["status"] == "pending"

    @patch("web.routes.job_routes.redis")
    @patch("web.routes.auth_routes.ReeleezeeClient")
    def test_list_jobs(self, mock_cls, mock_redis):
        mock_cls.return_value = self._mock_client()
        mock_redis.from_url.return_value = MagicMock()
        with patch("rq.Queue", return_value=MagicMock()):
            client = self._get_client()
            client.post("/api/login", json={"username": "u", "password": "p"})
            client.post("/api/jobs", json={
                "admin_id": "adm-1", "job_type": "data", "endpoints": ["customers"],
            })
            r = client.get("/api/jobs")
            assert r.status_code == 200
            assert len(r.json()) == 1
            assert r.json()[0]["admin_name"] == "Test"

    @patch("web.routes.job_routes.redis")
    @patch("web.routes.auth_routes.ReeleezeeClient")
    def test_get_job_detail_with_steps(self, mock_cls, mock_redis):
        mock_cls.return_value = self._mock_client()
        mock_redis.from_url.return_value = MagicMock()
        with patch("rq.Queue", return_value=MagicMock()):
            client = self._get_client()
            client.post("/api/login", json={"username": "u", "password": "p"})
            r = client.post("/api/jobs", json={
                "admin_id": "adm-1", "job_type": "data",
                "endpoints": ["customers", "vendors"],
            })
            job_id = r.json()["id"]
            r = client.get(f"/api/jobs/{job_id}")
            assert r.status_code == 200
            assert r.json()["id"] == job_id
            assert len(r.json()["steps"]) == 2

    @patch("web.routes.auth_routes.ReeleezeeClient")
    def test_get_job_not_found(self, mock_cls):
        mock_cls.return_value = self._mock_client()
        client = self._get_client()
        client.post("/api/login", json={"username": "u", "password": "p"})
        r = client.get("/api/jobs/nonexistent-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Data routes tests
# ---------------------------------------------------------------------------

class TestDataRoutes:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        _setup_test_env(str(tmp_path))
        self.tmp_path = tmp_path
        from web.database import init_db
        init_db()

    def _login_and_create_job(self, client):
        """Helper: login, create a job, and populate data files."""
        mock_c = MagicMock()
        mock_c.administrations = [{"id": "adm-1", "Name": "Test"}]
        with patch("web.routes.auth_routes.ReeleezeeClient", return_value=mock_c):
            client.post("/api/login", json={"username": "u", "password": "p"})

        with patch("web.routes.job_routes.redis") as mock_redis, \
             patch("rq.Queue", return_value=MagicMock()):
            mock_redis.from_url.return_value = MagicMock()
            r = client.post("/api/jobs", json={
                "admin_id": "adm-1", "job_type": "data",
                "endpoints": ["customers"],
            })
            job_id = r.json()["id"]

        # Create data files in the job directory
        from web import config
        job_dir = os.path.join(config.DATA_DIR, job_id, "adm-1")
        os.makedirs(job_dir, exist_ok=True)

        with open(os.path.join(job_dir, "customers.json"), "w") as f:
            json.dump({
                "type": "customers",
                "count": 2,
                "exported_at": "2025-01-01T00:00:00",
                "data": [
                    {"id": "c1", "Name": "Alice"},
                    {"id": "c2", "Name": "Bob"},
                ],
            }, f)

        return job_id

    def test_list_data_files(self):
        from web.app import create_app
        from fastapi.testclient import TestClient
        client = TestClient(create_app())

        job_id = self._login_and_create_job(client)
        r = client.get(f"/api/jobs/{job_id}/data")
        assert r.status_code == 200
        data = r.json()
        assert len(data["files"]) >= 1

    def test_get_paginated_data(self):
        from web.app import create_app
        from fastapi.testclient import TestClient
        client = TestClient(create_app())

        job_id = self._login_and_create_job(client)
        r = client.get(f"/api/jobs/{job_id}/data/customers?page=1&per_page=1")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["per_page"] == 1
        assert len(data["data"]) == 1
        assert data["data"][0]["Name"] == "Alice"

    def test_data_type_not_found(self):
        from web.app import create_app
        from fastapi.testclient import TestClient
        client = TestClient(create_app())

        job_id = self._login_and_create_job(client)
        r = client.get(f"/api/jobs/{job_id}/data/nonexistent")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Worker helper tests
# ---------------------------------------------------------------------------

class TestWorkerHelpers:

    def test_atomic_write_json(self):
        from web.workers.export_job import _atomic_write_json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "subdir" / "test.json"
            data = {"key": "value", "count": 42}

            _atomic_write_json(filepath, data)

            assert filepath.exists()
            with open(filepath) as f:
                loaded = json.load(f)
            assert loaded["key"] == "value"
            assert loaded["count"] == 42

    def test_update_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_test_env(tmpdir)
            from web.database import init_db, get_db
            from web.auth import encrypt_credentials, create_session

            init_db()
            encrypted = encrypt_credentials("u", "p")
            session_id = create_session(encrypted, [])

            # Insert a test job with valid session FK
            with get_db() as db:
                db.execute(
                    """INSERT INTO jobs (id, session_id, admin_id, admin_name,
                       job_type, endpoints, data_dir, encrypted_credentials)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("job-1", session_id, "adm-1", "Test", "data",
                     "[]", "/tmp/test", encrypted),
                )

            from web.workers.export_job import _update_job
            _update_job("job-1", status="running", current_step="customers")

            with get_db() as db:
                row = db.execute("SELECT * FROM jobs WHERE id = 'job-1'").fetchone()
            assert row["status"] == "running"
            assert row["current_step"] == "customers"

    def test_update_step(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_test_env(tmpdir)
            from web.database import init_db, get_db
            from web.auth import encrypt_credentials, create_session

            init_db()
            encrypted = encrypt_credentials("u", "p")
            session_id = create_session(encrypted, [])

            with get_db() as db:
                db.execute(
                    """INSERT INTO jobs (id, session_id, admin_id, admin_name,
                       job_type, endpoints, data_dir, encrypted_credentials)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("job-2", session_id, "adm-1", "Test", "data",
                     "[]", "/tmp/test", encrypted),
                )
                db.execute(
                    "INSERT INTO job_steps (job_id, step_name) VALUES (?, ?)",
                    ("job-2", "customers"),
                )

            from web.workers.export_job import _update_step
            _update_step("job-2", "customers", status="completed", items_count=72)

            with get_db() as db:
                step = db.execute(
                    "SELECT * FROM job_steps WHERE job_id = 'job-2'"
                ).fetchone()
            assert step["status"] == "completed"
            assert step["items_count"] == 72
