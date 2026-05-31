"""Assistant API: generate resources from natural language prompts."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.api import RETRY_HEADERS_30
from blackbeard.auth import get_current_user
from blackbeard.engine.assistant import (
    AssistantError,
    NoLLMConnectionError,
    generate_resources,
)
from blackbeard.kinds import NAME_PATTERN
from blackbeard.models import User, get_session
from blackbeard.rate_limiter import assistant_limiter, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantRequest(BaseModel):
    """Request body for resource generation."""

    prompt: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Natural language description of the crew to generate",
    )
    llm_connection: str | None = Field(
        default=None,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Name of the LLMConnection to use (uses first available if omitted)",
    )
    project: str = Field(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Project for the LLMConnection",
    )


class AssistantResponse(BaseModel):
    """Response with generated resources and explanation."""

    resources: list[dict[str, Any]] = Field(
        description="Generated YAML resource dicts (Agent, Task, Crew)"
    )
    explanation: str = Field(description="Brief explanation of what was generated")


class AssistantErrorResponse(BaseModel):
    """Error response from Assistant."""

    detail: str


@router.post(
    "/generate",
    response_model=AssistantResponse,
    responses={
        422: {"description": "Validation error (prompt too short/long)"},
        424: {
            "model": AssistantErrorResponse,
            "description": "No LLMConnection available in the specified project",
        },
        429: {"description": "Too many AI assist requests"},
        502: {
            "model": AssistantErrorResponse,
            "description": "LiteLLM proxy unreachable or model error",
        },
    },
)
async def generate_crew(
    body: AssistantRequest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> AssistantResponse:
    """Generate agents, tasks, and crew from a natural language prompt.

    Uses a configured LLMConnection via the LiteLLM proxy. If no
    llm_connection is specified, uses the first available LLMConnection
    in the given project.
    """
    check_rate_limit(assistant_limiter, user, "Too many AI assist requests. Try again later.")

    logger.info(
        "Assistant request: prompt_len=%d llm=%s project=%s user=%s",
        len(body.prompt),
        body.llm_connection or "(auto)",
        body.project,
        str(user.id) if user else "api-key",
        extra={
            "event": "assistant_api_request",
            "prompt_length": len(body.prompt),
            "llm_connection": body.llm_connection,
            "project": body.project,
            "user_id": str(user.id) if user else None,
        },
    )

    try:
        resources, explanation = await generate_resources(
            prompt=body.prompt,
            llm_connection_name=body.llm_connection,
            project=body.project,
            session=session,
        )
    except NoLLMConnectionError as e:
        logger.warning(
            "Assistant no LLMConnection: %s",
            e,
            exc_info=True,
            extra={"event": "assistant_no_llm"},
        )
        raise HTTPException(
            status_code=424,
            detail="No LLM connection available in the specified project.",
        ) from e
    except AssistantError as e:
        logger.warning(
            "Assistant error: %s",
            e,
            exc_info=True,
            extra={
                "event": "assistant_error",
                "error": str(e)[:500],
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Resource generation failed. Check server logs for details.",
            headers=RETRY_HEADERS_30,
        ) from e

    return AssistantResponse(resources=resources, explanation=explanation)
