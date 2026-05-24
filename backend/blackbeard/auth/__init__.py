"""Authentication and authorization package."""

from __future__ import annotations

from blackbeard.auth.api_key import get_api_key, set_api_key
from blackbeard.auth.authorizer import Authorizer
from blackbeard.auth.dependencies import (
    check_resource_permission,
    get_current_user,
    require_permission,
    require_user,
)
from blackbeard.auth.jwt import create_access_token, create_refresh_token, decode_token
from blackbeard.auth.passwords import hash_password, verify_password

__all__ = [
    "Authorizer",
    "check_resource_permission",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_api_key",
    "get_current_user",
    "hash_password",
    "require_permission",
    "require_user",
    "set_api_key",
    "verify_password",
]
