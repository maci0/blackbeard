"""Credentials API — centralized secret management.

Stores credentials (API keys, tokens, passwords) that can be
referenced by tools and LLM connections. Values are never returned
in full — only a masked preview is exposed.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from blackbeard.auth.dependencies import require_permission
from blackbeard.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials", tags=["credentials"])

# ---------------------------------------------------------------------------
# In-memory credential store (MVP — no separate table needed yet)
# ---------------------------------------------------------------------------

_credentials: dict[str, dict[str, Any]] = {}


def _mask(value: str) -> str:
    """Return a masked version of a secret value."""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


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
    created_at: str
    updated_at: str
    last_used_at: str | None
    masked_value: str


class CredentialListResponse(BaseModel):
    items: list[CredentialResponse]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_credential(
    body: CreateCredentialRequest,
    _current_user: User = Depends(
        require_permission("create", "Credential", require_identity=True)
    ),
) -> CredentialResponse:
    """Create a new credential."""
    if body.name in _credentials:
        raise HTTPException(status_code=409, detail=f"Credential '{body.name}' already exists")

    now = datetime.now(UTC).isoformat()
    cred_id = str(uuid.uuid4())
    _credentials[body.name] = {
        "id": cred_id,
        "name": body.name,
        "type": body.type,
        "description": body.description,
        "value_hash": hashlib.sha256(body.value.encode()).hexdigest(),
        "masked_value": _mask(body.value),
        "created_at": now,
        "updated_at": now,
        "last_used_at": None,
    }

    logger.info(
        "Credential created: %s",
        body.name,
        extra={
            "event": "credential_created",
            "name": body.name,
            "type": body.type,
        },
    )

    return CredentialResponse(
        id=cred_id,
        name=body.name,
        type=body.type,
        description=body.description,
        created_at=now,
        updated_at=now,
        last_used_at=None,
        masked_value=_mask(body.value),
    )


@router.get("")
async def list_credentials(
    _current_user: User = Depends(require_permission("list", "Credential", require_identity=True)),
) -> CredentialListResponse:
    """List all credentials (masked values only)."""
    items = [
        CredentialResponse(
            id=c["id"],
            name=c["name"],
            type=c["type"],
            description=c["description"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            last_used_at=c["last_used_at"],
            masked_value=c["masked_value"],
        )
        for c in sorted(_credentials.values(), key=lambda x: x["created_at"], reverse=True)
    ]
    return CredentialListResponse(items=items, total=len(items))


@router.delete("/{credential_id}")
async def delete_credential(
    credential_id: str,
    _current_user: User = Depends(
        require_permission("delete", "Credential", require_identity=True)
    ),
) -> dict[str, str]:
    """Delete a credential by ID."""
    for name, cred in _credentials.items():
        if cred["id"] == credential_id:
            del _credentials[name]
            logger.info(
                "Credential deleted: %s",
                name,
                extra={"event": "credential_deleted", "name": name},
            )
            return {"status": "deleted", "name": name}
    raise HTTPException(status_code=404, detail="Credential not found")
