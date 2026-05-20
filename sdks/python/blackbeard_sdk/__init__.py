"""Blackbeard SDK — Python client for the Blackbeard Agent Management Platform."""

from __future__ import annotations

from blackbeard_sdk.client import BlackbeardClient
from blackbeard_sdk.resources import KIND_TO_PLURAL

__version__ = "0.1.0"
__all__ = ["BlackbeardClient", "KIND_TO_PLURAL"]
