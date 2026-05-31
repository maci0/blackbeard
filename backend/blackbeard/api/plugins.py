"""REST API endpoints for plugin management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from blackbeard.auth.dependencies import require_permission
from blackbeard.models import User
from blackbeard.plugins import PluginType, registry
from blackbeard.plugins.loader import reload_plugin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginResponse(BaseModel):
    """Serialized plugin metadata."""

    name: str
    version: str
    description: str
    plugin_type: str
    entry_point: str


class PluginListResponse(BaseModel):
    """Response for the plugin list endpoint."""

    plugins: list[PluginResponse]
    count: int


class PluginReloadResponse(BaseModel):
    """Response for plugin reload."""

    name: str
    version: str
    status: str


@router.get(
    "",
    response_model=PluginListResponse,
    summary="List registered plugins",
)
async def list_plugins(
    plugin_type: str | None = None,
    _user: User | None = Depends(require_permission("list", "Plugin")),
) -> PluginListResponse:
    """List all registered plugins, optionally filtered by type."""
    pt: PluginType | None = None
    if plugin_type is not None:
        try:
            pt = PluginType(plugin_type)
        except ValueError:
            valid = ", ".join(t.value for t in PluginType)
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plugin_type '{plugin_type}'. Valid values: {valid}",
            ) from None

    metas = registry.list_plugins(pt)
    items = [
        PluginResponse(
            name=m.name,
            version=m.version,
            description=m.description,
            plugin_type=m.plugin_type.value,
            entry_point=m.entry_point,
        )
        for m in metas
    ]
    return PluginListResponse(plugins=items, count=len(items))


@router.post(
    "/{name}/reload",
    response_model=PluginReloadResponse,
    summary="Reload a plugin",
)
async def reload_plugin_endpoint(
    name: str,
    _user: User | None = Depends(require_permission("update", "Plugin")),
) -> PluginReloadResponse:
    """Reload a specific plugin by name.

    Re-imports the plugin module from disk and re-registers the handler.
    Useful for developing plugins without restarting the server.
    """
    meta = reload_plugin(name)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{name}' not found or reload failed. "
            "Check that the plugin was loaded at startup.",
        )
    return PluginReloadResponse(
        name=meta.name,
        version=meta.version,
        status="reloaded",
    )
