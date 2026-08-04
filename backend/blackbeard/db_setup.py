"""Idempotent database setup run by entrypoint.sh before the API starts.

Creates PostgreSQL enum types, tables (``Base.metadata.create_all`` creates new
tables only; Alembic handles schema evolution), and CHECK constraints that
SQLAlchemy models cannot express. Safe to run on every container start.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import text

import blackbeard.models.execution  # registers tables on Base.metadata
import blackbeard.models.resource
import blackbeard.models.user  # noqa: F401
from blackbeard.kinds import ResourceKind
from blackbeard.models.database import Base, engine
from blackbeard.models.execution import ExecutionStatus, ExecutionType, TaskStatus

if TYPE_CHECKING:
    from enum import Enum

_NAME_RE = r"^[a-z0-9][a-z0-9\-]*$"


def _create_enum_sql(type_name: str, enum_cls: type[Enum]) -> str:
    values = ",".join(f"'{v.value}'" for v in enum_cls)
    return (
        f"DO $$ BEGIN CREATE TYPE {type_name} AS ENUM ({values}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )


def _check_sql(table: str, constraint: str, column: str) -> str:
    return (
        f"DO $$ BEGIN ALTER TABLE {table} ADD CONSTRAINT {constraint} "
        f"CHECK ({column} ~ '{_NAME_RE}'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )


_PG_CHECKS = [
    _check_sql("resources", "ck_resource_name_pattern", "name"),
    _check_sql("resources", "ck_resource_project_pattern", "project"),
    _check_sql("executions", "ck_execution_crew_name_pattern", "crew_name"),
    _check_sql("executions", "ck_execution_crew_project_pattern", "crew_project"),
    _check_sql("resource_refs", "ck_ref_target_name_pattern", "target_name"),
    _check_sql("resource_refs", "ck_ref_target_project_pattern", "target_project"),
]


async def migrate() -> None:
    async with engine.begin() as conn:
        for stmt in [
            _create_enum_sql("resourcekind", ResourceKind),
            _create_enum_sql("executiontype", ExecutionType),
            _create_enum_sql("executionstatus", ExecutionStatus),
            _create_enum_sql("taskstatus", TaskStatus),
        ]:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _PG_CHECKS:
            await conn.execute(text(stmt))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
