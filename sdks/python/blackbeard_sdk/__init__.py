"""Blackbeard SDK — Python client for the Blackbeard Agent Management Platform."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from blackbeard_sdk.client import BlackbeardClient
from blackbeard_sdk.errors import BlackbeardApiError
from blackbeard_sdk.executions import TERMINAL_STATUSES
from blackbeard_sdk.resources import KIND_TO_PLURAL

try:
    __version__ = version("blackbeard-sdk")
except PackageNotFoundError:  # running from source without an installed dist
    __version__ = "0.0.0.dev0"
__all__ = [
    "KIND_TO_PLURAL",
    "TERMINAL_STATUSES",
    "BlackbeardApiError",
    "BlackbeardClient",
    "__version__",
]
