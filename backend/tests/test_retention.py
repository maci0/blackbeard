"""Tests for the data retention purge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from blackbeard.auth.passwords import hash_password
from blackbeard.config import settings
from blackbeard.models import AuditLog, Execution, User
from blackbeard.models.execution import ExecutionStatus
from blackbeard.retention import purge_expired_data, retention_enabled


def _audit(age_days: int) -> AuditLog:
    return AuditLog(
        timestamp=datetime.now(UTC) - timedelta(days=age_days),
        actor_type="user",
        actor_id="u1",
        action="test_action",
    )


def _execution(age_days: int, status: ExecutionStatus) -> Execution:
    ts = datetime.now(UTC) - timedelta(days=age_days)
    return Execution(
        crew_name="crew",
        status=status,
        created_at=ts,
        started_at=ts if status != ExecutionStatus.QUEUED else None,
        completed_at=ts if status == ExecutionStatus.COMPLETED else None,
    )


def _user(*, active: bool, age_days: int, email: str) -> User:
    ts = datetime.now(UTC) - timedelta(days=age_days)
    return User(
        email=email,
        display_name="Test User",
        password_hash=hash_password("testpass1"),
        is_active=active,
        created_at=ts,
        updated_at=ts,
    )


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_purge_disabled_by_default(db_session, monkeypatch):
    monkeypatch.setattr(settings, "audit_log_retention_days", None)
    monkeypatch.setattr(settings, "execution_retention_days", None)
    monkeypatch.setattr(settings, "user_retention_days", None)
    db_session.add(_audit(age_days=1000))
    await db_session.commit()

    assert not retention_enabled()
    purged = await purge_expired_data(db_session)
    assert purged == {"audit_logs": 0, "executions": 0, "users": 0}
    assert await _count(db_session, AuditLog) == 1


@pytest.mark.asyncio
async def test_purge_deletes_only_aged_rows(db_session, monkeypatch):
    monkeypatch.setattr(settings, "audit_log_retention_days", 30)
    monkeypatch.setattr(settings, "execution_retention_days", 30)
    monkeypatch.setattr(settings, "user_retention_days", None)
    db_session.add_all(
        [
            _audit(age_days=31),
            _audit(age_days=1),
            _execution(age_days=31, status=ExecutionStatus.COMPLETED),
            _execution(age_days=1, status=ExecutionStatus.COMPLETED),
        ]
    )
    await db_session.commit()

    assert retention_enabled()
    purged = await purge_expired_data(db_session)
    assert purged == {"audit_logs": 1, "executions": 1, "users": 0}
    assert await _count(db_session, AuditLog) == 1
    assert await _count(db_session, Execution) == 1


@pytest.mark.asyncio
async def test_purge_spares_running_executions(db_session, monkeypatch):
    monkeypatch.setattr(settings, "audit_log_retention_days", None)
    monkeypatch.setattr(settings, "execution_retention_days", 30)
    monkeypatch.setattr(settings, "user_retention_days", None)
    db_session.add(_execution(age_days=90, status=ExecutionStatus.RUNNING))
    await db_session.commit()

    purged = await purge_expired_data(db_session)
    assert purged["executions"] == 0
    assert await _count(db_session, Execution) == 1


@pytest.mark.asyncio
async def test_purge_hard_deletes_aged_deactivated_users(db_session, monkeypatch):
    monkeypatch.setattr(settings, "audit_log_retention_days", None)
    monkeypatch.setattr(settings, "execution_retention_days", None)
    monkeypatch.setattr(settings, "user_retention_days", 30)
    db_session.add_all(
        [
            _user(active=False, age_days=31, email="old-deleted@deactivated.local"),
            _user(active=False, age_days=1, email="recent-deleted@deactivated.local"),
            _user(active=True, age_days=90, email="active@example.com"),
        ]
    )
    await db_session.commit()

    assert retention_enabled()
    purged = await purge_expired_data(db_session)
    assert purged["users"] == 1
    assert await _count(db_session, User) == 2
