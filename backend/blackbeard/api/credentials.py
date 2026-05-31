"""Credentials API — centralized secret management.

Stores credentials (API keys, tokens, passwords) that can be
referenced by tools and LLM connections. Values are never returned
in full — only a masked preview is exposed.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.api import MUTATION_RATE_MSG as _MUTATION_RATE_MSG
from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import require_permission
from blackbeard.models import User, get_session
from blackbeard.rate_limiter import check_rate_limit, mutation_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials", tags=["credentials"])

# ---------------------------------------------------------------------------
# In-memory credential store (MVP — no separate table needed yet)
# ---------------------------------------------------------------------------

_credentials: dict[str, dict[str, Any]] = {}
_credentials_lock = threading.Lock()


# Fixed-width mask for all secret values — identical regardless of input
# to avoid leaking length, prefix, or suffix information (CWE-200).
_MASKED_VALUE = "****"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateCredentialRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    type: str = Field(default="api_key", max_length=50)
    value: str = Field(..., min_length=1, max_length=10_000)
    description: str = Field(default="", max_length=500)


class CredentialResponse(BaseModel):
    id: str
    name: str
    type: str
    description: str
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None
    masked_value: str


class CredentialListResponse(BaseModel):
    items: list[CredentialResponse]
    total: int
    limit: int = 100
    offset: int = 0
    has_more: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CredentialResponse,
    status_code=201,
    responses={
        409: {"description": "Credential with this name already exists"},
        429: {"description": "Too many mutation requests"},
    },
)
async def create_credential(
    body: CreateCredentialRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(
        require_permission("create", "Credential", require_identity=True)
    ),
) -> CredentialResponse:
    """Create a new credential."""
    check_rate_limit(mutation_limiter, _current_user, _MUTATION_RATE_MSG)
    now = datetime.now(UTC)
    cred_id = str(uuid.uuid4())
    with _credentials_lock:
        if body.name in _credentials:
            raise HTTPException(status_code=409, detail=f"Credential '{body.name}' already exists")
        _credentials[body.name] = {
            "id": cred_id,
            "name": body.name,
            "type": body.type,
            "description": body.description,
            "value_hash": hashlib.sha256(body.value.encode()).hexdigest(),
            "masked_value": _MASKED_VALUE,
            "created_at": now,
            "updated_at": now,
            "last_used_at": None,
        }

    await log_audit(
        session,
        action="credential_created",
        resource_type="Credential",
        resource_id=body.name,
        **audit_from_request(request, _current_user),
    )
    await session.commit()

    logger.info(
        "Credential created: %s",
        body.name,
        extra={
            "event": "credential_created",
            "credential_name": body.name,
            "credential_type": body.type,
        },
    )

    response.headers["Location"] = f"/api/v1/credentials/{cred_id}"
    return CredentialResponse(
        id=cred_id,
        name=body.name,
        type=body.type,
        description=body.description,
        created_at=now,
        updated_at=now,
        last_used_at=None,
        masked_value=_MASKED_VALUE,
    )


@router.get(
    "",
    response_model=CredentialListResponse,
    responses={
        200: {"description": "Paginated list of credentials (values masked)"},
    },
)
async def list_credentials(
    response: Response,
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_permission("list", "Credential", require_identity=True)),
) -> CredentialListResponse:
    """List all credentials (masked values only)."""
    response.headers["Cache-Control"] = "no-store"
    with _credentials_lock:
        all_creds = sorted(_credentials.values(), key=lambda x: x["created_at"], reverse=True)
    total = len(all_creds)
    page = all_creds[offset : offset + limit]
    items = [
        CredentialResponse(
            id=c["id"],
            name=c["name"],
            type=c["type"],
            description=c["description"],
            created_at=cast("datetime", c["created_at"]),
            updated_at=cast("datetime", c["updated_at"]),
            last_used_at=cast("datetime | None", c["last_used_at"]),
            masked_value=c["masked_value"],
        )
        for c in page
    ]
    return CredentialListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.delete(
    "/{credential_id}",
    status_code=204,
    responses={
        204: {"description": "Credential deleted (or did not exist — idempotent)"},
        429: {"description": "Too many mutation requests"},
    },
)
async def delete_credential(
    request: Request,
    credential_id: str = Path(
        ...,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    ),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(
        require_permission("delete", "Credential", require_identity=True)
    ),
) -> None:
    """Delete a credential by ID. Idempotent."""
    check_rate_limit(mutation_limiter, _current_user, _MUTATION_RATE_MSG)
    with _credentials_lock:
        target = next((n for n, c in _credentials.items() if c["id"] == credential_id), None)
        if target is None:
            logger.debug(
                "Delete no-op: credential %s not found",
                credential_id,
                extra={
                    "event": "credential_delete_noop",
                    "credential_id": credential_id,
                },
            )
            return
        del _credentials[target]
    await log_audit(
        session,
        action="credential_deleted",
        resource_type="Credential",
        resource_id=target,
        **audit_from_request(request, _current_user),
    )
    await session.commit()
    logger.info(
        "Credential deleted: %s",
        target,
        extra={"event": "credential_deleted", "credential_name": target},
    )
