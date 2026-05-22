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
import json as _json_mod
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

import blackbeard.models.audit  # registers audit log table
import blackbeard.models.execution  # registers execution tables
import blackbeard.models.resource  # registers resource tables
import blackbeard.models.user  # registers user/group tables
import blackbeard.models.webhook  # noqa: F401 — registers webhook table
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

    from sqlalchemy import event as _sa_event

    @_sa_event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fks(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()
        dbapi_conn.create_function(
            "jsonb_typeof",
            1,
            lambda v: type(_json_mod.loads(v)).__name__.replace("list", "array").replace("dict", "object")
            if isinstance(v, str)
            else None,
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
    # Clear rate-limit state so tests don't accumulate auth failures across runs
    from blackbeard.api.middleware import _auth_failures

    _auth_failures.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    _auth_failures.clear()


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


def _make_execution(
    *,
    crew_name: str = "test-crew",
    execution_type: str = "kickoff",
    status: str = "queued",
    inputs: dict | None = None,
    outputs: dict | None = None,
    error: str | None = None,
    total_tokens: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: str = "0",
    n_iterations: int | None = None,
    training_file: str | None = None,
    tasks: list | None = None,
    initiated_by: str | None = None,
    principal_chain: dict | None = None,
):
    """Build a detached Execution ORM object for unit tests (no DB needed)."""
    import uuid as _uuid
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime
    from decimal import Decimal as _Decimal

    from blackbeard.models.execution import Execution, ExecutionStatus, ExecutionType

    e = Execution()
    e.id = _uuid.uuid4()
    e.crew_name = crew_name
    e.crew_namespace = "default"
    e.execution_type = ExecutionType(execution_type)
    e.status = ExecutionStatus(status)
    e.inputs = inputs if inputs is not None else {}
    e.outputs = outputs
    e.error = error
    e.total_tokens = total_tokens
    e.prompt_tokens = prompt_tokens
    e.completion_tokens = completion_tokens
    e.cost_usd = _Decimal(cost_usd)
    e.n_iterations = n_iterations
    e.training_file = training_file
    e.initiated_by = _uuid.UUID(initiated_by) if initiated_by else None
    e.principal_chain = principal_chain
    e.created_at = _datetime.now(_UTC)
    e.started_at = None
    e.completed_at = None
    e.tasks = tasks if tasks is not None else []
    return e
