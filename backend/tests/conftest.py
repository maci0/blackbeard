"""Shared test configuration and fixtures.

IMPORTANT: The PostgreSQL-specific column types (JSONB, UUID) are monkey-patched
to SQLite-compatible equivalents here — *before* any blackbeard models are imported
— so that integration tests can use an in-memory SQLite database without requiring
a live PostgreSQL instance.
"""

# ---------------------------------------------------------------------------
# Enable debug mode so the default API key is accepted during tests.
# Must be set before blackbeard.config is imported.
# ---------------------------------------------------------------------------
import os as _os

_os.environ.setdefault("DEBUG", "true")

# ---------------------------------------------------------------------------
# Patch postgresql types → SQLite-compatible equivalents
# This must happen at import time, before any blackbeard module is loaded.
# ---------------------------------------------------------------------------
import uuid as _uuid_mod

import sqlalchemy.dialects.postgresql as _pg_dialect
from sqlalchemy import JSON
from sqlalchemy.types import String, TypeDecorator


class _UUIDAsString(TypeDecorator):
    """Drop-in replacement for postgresql.UUID that works on SQLite.

    Uses TypeDecorator so that process_bind_param / process_result_value are
    actually invoked by SQLAlchemy's bind/result pipeline.

    Accepts the `as_uuid` kwarg (used by the models) and stores values as a
    VARCHAR(36) string, converting uuid.UUID ↔ str transparently.
    """

    impl = String
    cache_ok = True

    def __init__(self, as_uuid: bool = False, *args, **kw):
        self.as_uuid = as_uuid
        # Remove as_uuid from kw before passing to String (it doesn't understand it)
        super().__init__(*args, length=36, **kw)

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return value
        if self.as_uuid:
            return _uuid_mod.UUID(value) if not isinstance(value, _uuid_mod.UUID) else value
        return value


_pg_dialect.JSONB = JSON  # type: ignore[attr-defined]
_pg_dialect.UUID = _UUIDAsString  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Standard fixtures (shared across all test modules)
# ---------------------------------------------------------------------------
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import blackbeard.models.execution  # registers execution tables
import blackbeard.models.resource  # registers resource tables
import blackbeard.models.user  # noqa: F401 — registers user/group tables
from blackbeard.kinds import ResourceKind
from blackbeard.main import app
from blackbeard.models.database import (
    Base,
    get_session,
)
from blackbeard.models.resource import Resource

API_KEY_HEADER = {"X-API-Key": "change-me-in-production"}


def has_validation_error(
    errors: list,
    field_contains: str = "",
    msg_contains: str = "",
) -> bool:
    """Return True if any ValidationError matches both optional substrings."""
    for e in errors:
        field_ok = not field_contains or field_contains in e.field
        msg_ok = not msg_contains or msg_contains.lower() in e.message.lower()
        if field_ok and msg_ok:
            return True
    return False


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite database and yield a single session for the test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession):
    """HTTP test client wired to the in-memory SQLite session."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Shared test helpers (used across multiple test modules)
# ---------------------------------------------------------------------------


def make_resource(kind: ResourceKind, name: str, spec: dict) -> Resource:
    """Create a detached Resource ORM object without a database session."""
    r = Resource()
    r.kind = kind
    r.name = name
    r.namespace = "default"
    r.spec = spec
    return r


def _resource_map(*resources: Resource) -> dict[str, Resource]:
    return {f"{r.kind.value}/{r.name}": r for r in resources}


def _agent_payload(name: str = "researcher") -> dict:
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Agent",
        "metadata": {"name": name, "namespace": "default"},
        "spec": {
            "role": "Research Analyst",
            "goal": "Find and synthesise information",
            "backstory": "Years of experience in research",
        },
    }
