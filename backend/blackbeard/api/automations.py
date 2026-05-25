"""REST API endpoints for automation triggers."""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, Response

if TYPE_CHECKING:
    from blackbeard.models import Execution
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import get_current_user
from blackbeard.engine import ExecutionError, ExecutionNotFoundError
from blackbeard.engine import executor as _executor_mod
from blackbeard.kinds import NAME_PATTERN
from blackbeard.models import User, get_session
from blackbeard.models.execution_schemas import ExecutionResponse, validate_inputs
from blackbeard.rate_limiter import record_auth_failure
from blackbeard.resources import ResourceNotFoundError, ResourceService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["automations"])


class TriggerRequest(BaseModel):
    """Request body for manually triggering an automation."""

    inputs: dict[str, Any] = Field(default_factory=dict, description="Override inputs")

    @model_validator(mode="after")
    def _validate_input_sizes(self) -> TriggerRequest:
        validate_inputs(self.inputs)
        return self


class WebhookTriggerRequest(BaseModel):
    """Request body for webhook-triggered automations."""

    secret: str = Field(..., min_length=1, max_length=255, description="Webhook secret")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Event payload inputs")

    @model_validator(mode="after")
    def _validate_input_sizes(self) -> WebhookTriggerRequest:
        validate_inputs(self.inputs)
        return self


class TriggerResponse(BaseModel):
    """Response after triggering an automation."""

    status: str
    automation_name: str
    execution: ExecutionResponse | None = None


async def _get_automation_spec(
    session: AsyncSession,
    name: str,
    namespace: str,
) -> dict[str, Any]:
    """Load an Automation resource spec or raise 404."""
    service = ResourceService(session)
    try:
        resource = await service.get("Automation", name, namespace)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return dict(resource.spec or {})


@router.post(
    "/automations/{name}/trigger",
    response_model=TriggerResponse,
    status_code=202,
    responses={
        404: {"description": "Automation not found"},
        409: {"description": "Automation is disabled"},
        500: {"description": "Trigger execution failed"},
    },
)
async def trigger_automation(
    request: Request,
    response: Response,
    name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Automation name",
    ),
    body: TriggerRequest = Body(...),
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Namespace",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> TriggerResponse:
    """Manually trigger an automation via API."""
    spec = await _get_automation_spec(session, name, namespace)

    if not spec.get("enabled", True):
        raise HTTPException(status_code=409, detail=f"Automation '{name}' is disabled")

    target = spec.get("target", {})
    merged_inputs = {**spec.get("inputs", {}), **body.inputs}
    target_namespace = spec.get("namespace", namespace)

    execution = await _execute_target(session, target, merged_inputs, target_namespace, user)

    await log_audit(
        session,
        action="automation_triggered",
        resource_type="Automation",
        resource_id=name,
        detail={
            "trigger": "api",
            "target_kind": target.get("kind"),
            "target_name": target.get("name"),
        },
        **audit_from_request(request, user),
    )
    await session.commit()

    if execution is not None:
        response.headers["Location"] = f"/api/v1/executions/{execution.id}"

    logger.info(
        "Automation '%s' triggered via API: %s/%s",
        name,
        target.get("kind"),
        target.get("name"),
        extra={
            "event": "automation_api_trigger",
            "automation_name": name,
            "target_kind": target.get("kind"),
            "target_name": target.get("name"),
            "namespace": target_namespace,
        },
    )

    return TriggerResponse(
        status="triggered",
        automation_name=name,
        execution=ExecutionResponse.from_db(execution) if execution else None,
    )


@router.post(
    "/automations/{name}/webhook",
    response_model=TriggerResponse,
    status_code=202,
    responses={
        401: {"description": "Invalid webhook secret"},
        404: {"description": "Automation not found"},
        409: {"description": "Automation is disabled or not a webhook trigger"},
        500: {"description": "Trigger execution failed"},
    },
)
async def webhook_trigger(
    request: Request,
    response: Response,
    name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Automation name",
    ),
    body: WebhookTriggerRequest = Body(...),
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Namespace",
    ),
    session: AsyncSession = Depends(get_session),
) -> TriggerResponse:
    """Trigger an automation via external webhook (validates secret)."""
    spec = await _get_automation_spec(session, name, namespace)

    if not spec.get("enabled", True):
        raise HTTPException(status_code=409, detail=f"Automation '{name}' is disabled")

    trigger = spec.get("trigger", {})
    if trigger.get("type") != "webhook":
        raise HTTPException(
            status_code=409,
            detail=f"Automation '{name}' is not a webhook trigger",
        )

    expected_secret = trigger.get("webhook_secret", "")
    secret_valid = (
        bool(expected_secret)
        and len(expected_secret) >= 16
        and len(body.secret) >= 16
        and hmac.compare_digest(body.secret, expected_secret)
    )
    if not secret_valid:
        client_ip = request.client.host if request.client else "unknown"
        record_auth_failure(client_ip)
        logger.warning(
            "Webhook auth failed for automation '%s'",
            name,
            extra={
                "event": "webhook_auth_failed",
                "automation_name": name,
                "client_ip": client_ip,
            },
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook secret",
            headers={"WWW-Authenticate": "HMAC-SHA256"},
        )

    target = spec.get("target", {})
    merged_inputs = {**spec.get("inputs", {}), **body.inputs}
    target_namespace = spec.get("namespace", namespace)

    execution = await _execute_target(session, target, merged_inputs, target_namespace, user=None)

    await log_audit(
        session,
        action="automation_triggered",
        resource_type="Automation",
        resource_id=name,
        detail={
            "trigger": "webhook",
            "target_kind": target.get("kind"),
            "target_name": target.get("name"),
        },
        actor_type="webhook",
        actor_id=f"webhook:{name}",
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()

    if execution is not None:
        response.headers["Location"] = f"/api/v1/executions/{execution.id}"

    logger.info(
        "Automation '%s' triggered via webhook: %s/%s",
        name,
        target.get("kind"),
        target.get("name"),
        extra={
            "event": "automation_webhook_trigger",
            "automation_name": name,
            "target_kind": target.get("kind"),
            "target_name": target.get("name"),
            "namespace": target_namespace,
        },
    )

    return TriggerResponse(
        status="triggered",
        automation_name=name,
        execution=ExecutionResponse.from_db(execution) if execution else None,
    )


async def _execute_target(
    session: AsyncSession,
    target: dict[str, Any],
    inputs: dict[str, Any],
    namespace: str,
    user: User | None,
) -> Execution | None:
    """Execute the target Crew or Flow."""
    target_kind = target.get("kind", "Crew")
    target_name = target.get("name", "")

    try:
        if target_kind == "Flow":
            return await _executor_mod.run_flow(
                session,
                target_name,
                inputs=inputs,
                namespace=namespace,
                user=user,
            )
        return await _executor_mod.kickoff(
            session,
            target_name,
            inputs=inputs,
            namespace=namespace,
            user=user,
        )
    except ExecutionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"{target_kind} '{target_name}' not found",
        ) from exc
    except ExecutionError as exc:
        logger.error(
            "Automation trigger execution failed: %s/%s: %s",
            target_kind,
            target_name,
            exc,
            exc_info=True,
            extra={
                "event": "automation_execute_failed",
                "target_kind": target_kind,
                "target_name": target_name,
                "namespace": namespace,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Execution could not be created. Check server logs.",
        ) from exc
