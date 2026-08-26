"""MuninnDB memory backend for CrewAI agents.

Provides cognitive memory with temporal priority, Hebbian learning,
and semantic triggers via MuninnDB.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import muninn  # noqa: F401  (presence check only)

    HAS_MUNINN = True
except ImportError:
    HAS_MUNINN = False


class MuninnMemoryBackend:
    """Wraps MuninnDB as a memory store for CrewAI agents.

    MuninnDB is a cognitive memory database that strengthens with use,
    fades when unused, and pushes relevant information when it matters.

    The adapter translates CrewAI memory operations into MuninnDB's
    ``write()`` and ``activate()`` calls, using vaults for project
    isolation and tags for per-agent scoping.
    """

    def __init__(
        self,
        url: str = "http://localhost:8475",
        agent_name: str = "default",
        project: str = "default",
        vault: str | None = None,
        token: str | None = None,
    ) -> None:
        """Initialize the MuninnDB memory backend.

        Args:
            url: MuninnDB server URL.
            agent_name: Name of the agent using this memory backend.
            project: Blackbeard resource project for scoping.
            vault: MuninnDB vault name. Defaults to the project.
            token: Optional API token for MuninnDB authentication.
        """
        if not HAS_MUNINN:
            raise ImportError(
                "muninn-python package is not installed. Install it with: uv add muninn-python"
            )
        self._url = url
        self._agent_name = agent_name
        self._project = project
        self._vault = vault or project
        self._token = token

    def _make_client(self) -> Any:
        """Create a new MuninnClient instance.

        Each call creates a fresh client to avoid holding open connections
        across the executor thread pool boundary.

        Returns:
            A ``MuninnClient`` instance (typed as ``Any`` because the
            ``muninn`` package is an optional dependency).
        """
        from muninn import MuninnClient as _MuninnClient

        kwargs: dict[str, Any] = {"url": self._url}
        if self._token:
            kwargs["token"] = self._token
        return _MuninnClient(**kwargs)

    async def store(
        self,
        content: str,
        concept: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
    ) -> str:
        """Store a memory in MuninnDB.

        Args:
            content: The memory content to store.
            concept: Concept label for the memory. Defaults to ``"agent_memory"``.
            tags: Tags for categorization. Defaults to agent name and project.
            confidence: Optional confidence score (0.0-1.0).

        Returns:
            The engram ID of the stored memory.
        """
        write_kwargs: dict[str, Any] = {
            "vault": self._vault,
            "concept": concept or "agent_memory",
            "content": content,
            "tags": tags or [self._agent_name, self._project],
        }
        if confidence is not None:
            write_kwargs["confidence"] = confidence

        async with self._make_client() as client:
            result = await client.write(**write_kwargs)
        engram_id = str(result.id) if hasattr(result, "id") else str(result)
        logger.debug(
            "MuninnDB stored engram %s for agent '%s'",
            engram_id,
            self._agent_name,
            extra={
                "event": "muninn_store",
                "agent_name": self._agent_name,
                "concept": write_kwargs["concept"],
                "vault": self._vault,
            },
        )
        return engram_id

    async def recall(
        self,
        context: str,
        limit: int = 10,
        threshold: float = 0.2,
        include_why: bool = True,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant memories from MuninnDB.

        Args:
            context: The query context to activate memories against.
            limit: Maximum number of results to return.
            threshold: Minimum score threshold for results.
            include_why: Whether to include explainability data.

        Returns:
            List of dicts with ``content``, ``concept``, ``score``, and
            optionally ``confidence`` and ``why`` fields.
        """
        async with self._make_client() as client:
            result = await client.activate(
                vault=self._vault,
                context=[context],
                max_results=limit,
                threshold=threshold,
                include_why=include_why,
            )

        memories: list[dict[str, Any]] = []
        for item in result.activations:
            entry: dict[str, Any] = {
                "content": item.content,
                "concept": item.concept,
                "score": item.score,
            }
            if hasattr(item, "confidence"):
                entry["confidence"] = item.confidence
            if include_why and hasattr(item, "why"):
                entry["why"] = item.why
            memories.append(entry)

        logger.debug(
            "MuninnDB recalled %d memories for context (agent='%s')",
            len(memories),
            self._agent_name,
            extra={
                "event": "muninn_recall",
                "agent_name": self._agent_name,
                "result_count": len(memories),
                "vault": self._vault,
            },
        )
        return memories

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Synchronous search for CrewAI compatibility.

        CrewAI's memory system calls memory backends synchronously.
        This method bridges the async MuninnDB client by running the
        coroutine in a dedicated event loop.

        Args:
            query: The search query string.
            limit: Maximum number of results.

        Returns:
            List of memory dicts (same format as :meth:`recall`).
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.recall(query, limit))
        finally:
            loop.close()
