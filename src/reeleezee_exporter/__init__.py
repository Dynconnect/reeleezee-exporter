"""
Reeleezee Exporter - Export all your data from Reeleezee (Exact) accounting platform.

This package provides tools to export administrations, invoices, customers,
vendors, products, bank data, and document files from Reeleezee via their REST API.
"""

__version__ = "1.0.0"

from .client import AuthenticationError, ReeleezeeClient

__all__ = ["AuthenticationError", "ReeleezeeClient"]
