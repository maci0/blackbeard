"""Authentication and authorization package.

- ``api_key``: process-wide API key getter/setter
- ``jwt``: access/refresh token create and decode
- ``passwords``: hash/verify helpers
- ``authorizer``: RBAC evaluation against Role/RoleBinding resources
- ``dependencies``: FastAPI deps (``require_permission``, user/JWT guards)

Import from this package root for the stable surface listed in ``__all__``.
"""

from __future__ import annotations

from blackbeard.auth.api_key import get_api_key, set_api_key, verify_system_api_key
from blackbeard.auth.authorizer import Authorizer
from blackbeard.auth.dependencies import (
    SSE_STREAM_RE,
    bearer_401,
    check_resource_permission,
    get_current_user,
    require_jwt_user,
    require_permission,
    require_user,
    validate_ws_auth,
)
from blackbeard.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_token,
)
from blackbeard.auth.passwords import hash_password, secrets_equal, verify_password

__all__ = [
    "SSE_STREAM_RE",
    "Authorizer",
    "bearer_401",
    "check_resource_permission",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_token",
    "get_api_key",
    "get_current_user",
    "hash_password",
    "require_jwt_user",
    "require_permission",
    "require_user",
    "secrets_equal",
    "set_api_key",
    "validate_ws_auth",
    "verify_password",
    "verify_system_api_key",
]
