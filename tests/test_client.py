"""Tests for the Reeleezee API client."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest


class TestReeleezeeClient:
    """Tests for ReeleezeeClient authentication and request handling."""

    @patch("reeleezee_exporter.client.requests.Session")
    def test_authentication_sets_basic_auth_header(self, mock_session_class):
        """Verify that the client sets the correct Basic Auth header."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Mock successful auth response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [{"id": "test-admin-id", "Name": "Test Admin"}]
        }
        mock_session.get.return_value = mock_response

        from reeleezee_exporter.client import ReeleezeeClient

        client = ReeleezeeClient("testuser", "testpass")

        # Verify auth header was set
        expected_creds = base64.b64encode(b"testuser:testpass").decode()
        mock_session.headers.update.assert_any_call({
            "Authorization": f"Basic {expected_creds}",
            "Accept": "application/json",
        })

        # Verify administrations were stored
        assert len(client.administrations) == 1
        assert client.administrations[0]["id"] == "test-admin-id"

    @patch("reeleezee_exporter.client.requests.Session")
    def test_authentication_failure_raises_error(self, mock_session_class):
        """Verify that failed authentication raises AuthenticationError."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.get.return_value = mock_response

        from reeleezee_exporter.client import AuthenticationError, ReeleezeeClient

        with pytest.raises(AuthenticationError):
            ReeleezeeClient("baduser", "badpass")

    @patch("reeleezee_exporter.client.requests.Session")
    def test_get_json_unwraps_odata_value(self, mock_session_class):
        """Verify that OData responses with 'value' key are unwrapped."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Auth response
        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "value": [{"id": "admin-1", "Name": "Admin"}]
        }

        # Data response
        data_response = MagicMock()
        data_response.status_code = 200
        data_response.json.return_value = {
            "value": [{"id": "item-1"}, {"id": "item-2"}]
        }
        data_response.raise_for_status = MagicMock()

        mock_session.get.side_effect = [auth_response, data_response]

        from reeleezee_exporter.client import ReeleezeeClient

        client = ReeleezeeClient("user", "pass")
        result = client.get_json("SomeEndpoint")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "item-1"

    @patch("reeleezee_exporter.client.requests.Session")
    def test_get_paginated_follows_next_link(self, mock_session_class):
        """Verify that pagination follows @odata.nextLink."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "value": [{"id": "admin-1", "Name": "Admin"}]
        }

        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            "value": [{"id": "1"}, {"id": "2"}],
            "@odata.nextLink": "https://portal.reeleezee.nl/api/v1/next",
        }
        page1_response.raise_for_status = MagicMock()

        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            "value": [{"id": "3"}],
        }
        page2_response.raise_for_status = MagicMock()

        mock_session.get.side_effect = [auth_response, page1_response, page2_response]

        from reeleezee_exporter.client import ReeleezeeClient

        client = ReeleezeeClient("user", "pass")
        result = client.get_paginated("SomeEndpoint", verbose=False)

        assert len(result) == 3
        assert result[2]["id"] == "3"

    @patch("reeleezee_exporter.client.requests.Session")
    def test_download_returns_bytes_on_success(self, mock_session_class):
        """Verify that download returns bytes on successful response."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "value": [{"id": "admin-1", "Name": "Admin"}]
        }

        download_response = MagicMock()
        download_response.status_code = 200
        download_response.content = b"%PDF-1.4 fake pdf content"

        mock_session.get.side_effect = [auth_response, download_response]

        from reeleezee_exporter.client import ReeleezeeClient

        client = ReeleezeeClient("user", "pass")
        result = client.download("some/file/Download")

        assert result == b"%PDF-1.4 fake pdf content"

    @patch("reeleezee_exporter.client.requests.Session")
    def test_download_returns_none_on_failure(self, mock_session_class):
        """Verify that download returns None on non-200 response."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "value": [{"id": "admin-1", "Name": "Admin"}]
        }

        download_response = MagicMock()
        download_response.status_code = 404
        download_response.content = b""

        mock_session.get.side_effect = [auth_response, download_response]

        from reeleezee_exporter.client import ReeleezeeClient

        client = ReeleezeeClient("user", "pass")
        result = client.download("nonexistent/Download")

        assert result is None
