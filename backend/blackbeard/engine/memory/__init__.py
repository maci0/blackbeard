"""Memory backends for CrewAI agents.

Backends adapt external stores to CrewAI memory operations. Import the
concrete backend you need (e.g. ``from blackbeard.engine.memory.muninn
import MuninnMemoryBackend``). Keep new backends in this package.
"""

from __future__ import annotations

from blackbeard.engine.memory.muninn import HAS_MUNINN, MuninnMemoryBackend

__all__ = [
    "HAS_MUNINN",
    "MuninnMemoryBackend",
]
