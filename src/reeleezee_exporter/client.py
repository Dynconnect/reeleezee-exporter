"""
Reeleezee API client with authentication and pagination support.

Handles Basic Auth authentication and OData-style pagination
for the Reeleezee REST API at portal.reeleezee.nl/api/v1/.
"""

import base64
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests


class AuthenticationError(Exception):
    """Raised when authentication with the Reeleezee API fails."""


class ReeleezeeClient:
    """Low-level client for the Reeleezee REST API.

    Authenticates via HTTP Basic Auth (username/password) and provides
    methods for paginated GET requests following OData conventions.
    """

    BASE_URL = "https://portal.reeleezee.nl/api/v1/"

    def __init__(self, username: str, password: str):
        """Create an authenticated API session.

        Args:
            username: Reeleezee account username.
            password: Reeleezee account password.

        Raises:
            AuthenticationError: If authentication fails.
        """
        self.session = requests.Session()
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
        })

        # Verify authentication
        r = self.session.get(urljoin(self.BASE_URL, "Administrations"), timeout=15)
        if r.status_code != 200:
            raise AuthenticationError(f"Authentication failed: HTTP {r.status_code}")

        admins = r.json().get("value", [])
        if not admins:
            raise AuthenticationError("No administrations found for this account")

        self.administrations = admins
        print(f"Authenticated. Found {len(admins)} administration(s).")

    def get(self, endpoint: str, params: Optional[Dict] = None,
            timeout: int = 30, accept: str = "application/json") -> requests.Response:
        """Make a GET request to the API.

        Args:
            endpoint: API endpoint path (appended to BASE_URL).
            params: Optional query parameters.
            timeout: Request timeout in seconds.
            accept: Accept header value.

        Returns:
            The raw Response object.
        """
        url = urljoin(self.BASE_URL, endpoint)
        headers = {"Accept": accept} if accept != "application/json" else {}
        return self.session.get(url, params=params, timeout=timeout, headers=headers)

    def get_json(self, endpoint: str, params: Optional[Dict] = None,
                 timeout: int = 30) -> Any:
        """Make a GET request and return the JSON response.

        For OData responses with a ``value`` key, returns the value directly.

        Args:
            endpoint: API endpoint path.
            params: Optional query parameters.
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON data (unwrapped from OData ``value`` if present).

        Raises:
            requests.HTTPError: On non-2xx responses.
        """
        url = urljoin(self.BASE_URL, endpoint)
        r = self.session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        result = r.json()

        # Unwrap OData format: {"value": [...]}
        if isinstance(result, dict) and "value" in result:
            return result["value"]
        return result

    def get_paginated(self, endpoint: str, params: Optional[Dict] = None,
                      max_pages: Optional[int] = None,
                      verbose: bool = True) -> List[Dict]:
        """Fetch all pages from a paginated OData endpoint.

        Follows ``@odata.nextLink`` to retrieve all items across pages.

        Args:
            endpoint: API endpoint path.
            params: Optional query parameters for the first request.
            max_pages: Maximum number of pages to fetch (None for all).
            verbose: Whether to print progress.

        Returns:
            List of all items across all pages.
        """
        all_items: List[Dict] = []
        page = 0
        next_link: Optional[str] = None
        url = urljoin(self.BASE_URL, endpoint)

        while True:
            if max_pages and page >= max_pages:
                break

            page += 1

            try:
                if next_link:
                    r = self.session.get(next_link, timeout=30)
                else:
                    r = self.session.get(url, params=params, timeout=30)

                r.raise_for_status()
                result = r.json()

                if isinstance(result, dict):
                    items = result.get("value", [])
                    next_link = result.get("@odata.nextLink")

                    if isinstance(items, list) and items:
                        all_items.extend(items)
                        if verbose and (page % 5 == 0 or not next_link):
                            print(f"    Page {page}: {len(all_items)} items total")
                    else:
                        break

                    if not next_link:
                        break
                elif isinstance(result, list):
                    all_items.extend(result)
                    break
                else:
                    break

            except Exception as e:
                if verbose:
                    print(f"    Warning: error on page {page}: {e}")
                break

        if verbose and all_items:
            print(f"    Total: {len(all_items)} items from {page} page(s)")
        return all_items

    def download(self, endpoint: str, timeout: int = 60) -> Optional[bytes]:
        """Download binary content from an endpoint.

        Args:
            endpoint: API endpoint path.
            timeout: Request timeout in seconds.

        Returns:
            File content as bytes, or None on failure.
        """
        url = urljoin(self.BASE_URL, endpoint)
        try:
            r = self.session.get(url, timeout=timeout, headers={"Accept": "*/*"})
            if r.status_code == 200 and len(r.content) > 0:
                return r.content
            return None
        except Exception:
            return None
