"""Database engine and session factory."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from blackbeard.config import settings
from blackbeard.logging_config import request_id_var

logger = logging.getLogger(__name__)

_SLOW_QUERY_THRESHOLD_S = 1.0

engine = create_async_engine(
    settings.database_url.get_secret_value(),
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
    connect_args={
        "server_settings": {
            "statement_timeout": "30000",
            "idle_in_transaction_session_timeout": "60000",
        },
        "command_timeout": 10,
    },
)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: Any,
    parameters: Any,
    context: Any,
    executemany: Any,
) -> None:
    conn.info["query_start_time"] = time.monotonic()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: Any,
    parameters: Any,
    context: Any,
    executemany: Any,
) -> None:
    start = conn.info.pop("query_start_time", None)
    if start is None:
        return
    elapsed_s = time.monotonic() - start
    if elapsed_s >= _SLOW_QUERY_THRESHOLD_S:
        logger.warning(
            "Slow query: %.1fs %s",
            elapsed_s,
            statement[:200],
            extra={
                "event": "slow_query",
                "duration_s": round(elapsed_s, 2),
                "statement_preview": statement[:200],
                "request_id": request_id_var.get("-"),
            },
        )


@event.listens_for(engine.sync_engine, "checkout")
def _on_checkout(_dbapi_conn: Any, _connection_rec: Any, _connection_proxy: Any) -> None:
    pool = cast("Any", engine.sync_engine.pool)
    checked_out = pool.checkedout()
    pool_size = pool.size()
    overflow = pool.overflow()
    max_total = pool_size + overflow
    if max_total > 0 and checked_out >= max_total:
        logger.error(
            "DB pool exhausted: checked_out=%d/%d overflow=%d",
            checked_out,
            max_total,
            overflow,
            extra={
                "event": "db_pool_exhausted",
                "pool_size": pool_size,
                "pool_checked_out": checked_out,
                "pool_overflow": overflow,
                "pool_max_total": max_total,
                "request_id": request_id_var.get("-"),
            },
        )
    elif max_total > 0 and checked_out / max_total >= 0.8:
        logger.warning(
            "DB pool near exhaustion: checked_out=%d/%d overflow=%d",
            checked_out,
            max_total,
            overflow,
            extra={
                "event": "db_pool_near_exhaustion",
                "pool_size": pool_size,
                "pool_checked_out": checked_out,
                "pool_overflow": overflow,
                "pool_max_total": max_total,
                "request_id": request_id_var.get("-"),
            },
        )
    elif logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "DB pool checkout: size=%d checked_out=%d overflow=%d",
            pool_size,
            checked_out,
            overflow,
            extra={
                "event": "db_pool_checkout",
                "pool_size": pool_size,
                "pool_checked_out": checked_out,
                "pool_overflow": overflow,
            },
        )


_LONG_CHECKOUT_THRESHOLD_S = 5.0


@event.listens_for(engine.sync_engine, "checkin")
def _on_checkin(_dbapi_conn: Any, connection_rec: Any) -> None:
    start = connection_rec.info.pop("_bb_checkout_time", None)
    if start is not None:
        held_s = time.monotonic() - start
        if held_s >= _LONG_CHECKOUT_THRESHOLD_S:
            logger.warning(
                "DB connection held for %.1fs (threshold %.1fs)",
                held_s,
                _LONG_CHECKOUT_THRESHOLD_S,
                extra={
                    "event": "db_connection_held_long",
                    "held_s": round(held_s, 2),
                    "threshold_s": _LONG_CHECKOUT_THRESHOLD_S,
                },
            )


@event.listens_for(engine.sync_engine, "checkout")
def _stamp_checkout_time(_dbapi_conn: Any, connection_rec: Any, _connection_proxy: Any) -> None:
    connection_rec.info["_bb_checkout_time"] = time.monotonic()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Dependency that yields a database session."""
    async with async_session() as session:
        yield session
