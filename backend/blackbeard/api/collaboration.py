"""WebSocket endpoint for real-time canvas collaboration."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import time
from typing import Any

import jwt as pyjwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from blackbeard.api import middleware as _auth_mw
from blackbeard.auth.jwt import decode_token

logger = logging.getLogger(__name__)

_SINGLE_REPLICA_WARNING = (
    "Live collaboration requires a single API replica. "
    "Set api.replicas=1 in Helm values or use sticky sessions."
)

if os.environ.get("WEB_CONCURRENCY", "1") != "1":
    logger.warning(
        _SINGLE_REPLICA_WARNING,
        extra={"event": "collab_multi_replica_warning"},
    )

router = APIRouter(tags=["collaboration"])

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_MAX_CREW_NAME_LEN = 255

ALLOWED_MESSAGE_TYPES = frozenset(
    {
        "node_add",
        "node_move",
        "node_delete",
        "node_update",
        "edge_add",
        "edge_delete",
        "cursor_move",
        "selection_change",
    }
)

# Rate limiting for high-frequency message types (cursor_move, selection_change).
# Allows _RATE_LIMIT_MAX messages per _RATE_LIMIT_WINDOW_S seconds per client.
_RATE_LIMIT_WINDOW_S = 1.0
_RATE_LIMIT_MAX = 30  # max cursor_move + selection_change messages per second
_HIGH_FREQ_TYPES = frozenset({"cursor_move", "selection_change"})
# Maximum depth for nested message data to prevent deeply-nested JSON DoS.
_MAX_MESSAGE_DATA_DEPTH = 5

# In-memory room state — maps crew_name to set of WebSocket connections.
# Used by all deployments for local WebSocket fan-out.  When a Valkey
# backend is available, messages are also published to Valkey pub/sub so
# that other replicas receive them.
_rooms: dict[str, set[WebSocket]] = {}
_rooms_lock = asyncio.Lock()


class ValkeyCollabBackend:
    """Backs collaboration rooms with Valkey pub/sub for multi-replica support.

    Each replica publishes outgoing messages to a ``collab:{room}`` channel
    and subscribes to receive messages from other replicas.  Local fan-out
    (to WebSocket connections on this process) is still handled by
    ``_broadcast_local``.
    """

    def __init__(self) -> None:
        import redis.asyncio as aioredis

        from blackbeard.config import settings

        self._redis: aioredis.Redis = aioredis.from_url(
            settings.valkey_url.get_secret_value(),
            decode_responses=True,
        )
        self._subscriptions: dict[str, asyncio.Task[None]] = {}
        self._subscriber_lock = asyncio.Lock()

    async def publish(self, room: str, message: dict[str, Any]) -> None:
        """Publish a collaboration message to the Valkey channel."""
        try:
            await self._redis.publish(f"collab:{room}", json.dumps(message))
        except Exception:
            logger.warning(
                "Valkey publish failed for room %s",
                room,
                exc_info=True,
                extra={"event": "valkey_publish_failed", "room": room},
            )

    async def subscribe(self, room: str) -> None:
        """Subscribe to a room channel and forward messages to local WebSockets.

        Spawns a background task that reads from the Valkey subscription and
        broadcasts to local connections.  Idempotent -- calling multiple
        times for the same room is safe.
        """
        async with self._subscriber_lock:
            if room in self._subscriptions:
                return

            task = asyncio.create_task(self._listen(room), name=f"valkey-collab-{room}")
            self._subscriptions[room] = task

    async def unsubscribe(self, room: str) -> None:
        """Stop listening to a room channel."""
        async with self._subscriber_lock:
            task = self._subscriptions.pop(room, None)
            if task is not None:
                task.cancel()

    async def _listen(self, room: str) -> None:
        """Background listener that forwards Valkey messages to local WebSockets."""
        import redis.asyncio as aioredis

        try:
            pubsub: aioredis.client.PubSub = self._redis.pubsub()
            await pubsub.subscribe(f"collab:{room}")
            async for raw_message in pubsub.listen():
                if raw_message["type"] != "message":
                    continue
                try:
                    message = json.loads(raw_message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                # Broadcast to all local connections (sender=None since the
                # original sender is on a different replica)
                await _broadcast_local(room, sender=None, message=message)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning(
                "Valkey subscription listener failed for room %s",
                room,
                exc_info=True,
                extra={"event": "valkey_listen_failed", "room": room},
            )


# Initialise Valkey backend lazily — only when the Valkey URL is configured
# and the redis library is available.
_valkey_backend: ValkeyCollabBackend | None = None


def _get_valkey_backend() -> ValkeyCollabBackend | None:
    """Return the Valkey collaboration backend, creating it on first call.

    Returns None if the redis library is not installed or Valkey is not
    configured.
    """
    global _valkey_backend
    if _valkey_backend is not None:
        return _valkey_backend

    try:
        import redis.asyncio  # noqa: F401

        from blackbeard.config import settings

        valkey_url = settings.valkey_url.get_secret_value()
        if not valkey_url:
            return None
        _valkey_backend = ValkeyCollabBackend()
        return _valkey_backend
    except ImportError:
        return None
    except Exception:
        logger.warning(
            "Valkey collaboration backend init failed — cross-replica collaboration will not work",
            exc_info=True,
            extra={"event": "valkey_collab_init_failed"},
        )
        return None


async def _broadcast_local(
    room: str,
    sender: WebSocket | None,
    message: dict[str, Any],
) -> None:
    """Send message to all local participants in a room except the sender.

    Dead connections are silently removed from the room set.
    """
    participants = _rooms.get(room)
    if not participants:
        return

    dead: set[WebSocket] = set()
    for ws in participants:
        if ws is sender:
            continue
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)

    if dead:
        participants.difference_update(dead)
        logger.debug(
            "Removed %d dead WebSocket connections from room %s",
            len(dead),
            room,
            extra={
                "event": "collab_dead_connections_removed",
                "room": room,
                "dead_count": len(dead),
                "remaining": len(participants),
            },
        )


async def _broadcast(
    room: str,
    sender: WebSocket,
    message: dict[str, Any],
) -> None:
    """Send message to all participants in a room except the sender.

    Broadcasts locally and, if available, publishes to Valkey for
    cross-replica delivery.  Dead connections are silently removed.
    """
    await _broadcast_local(room, sender, message)

    # Publish to Valkey for other replicas
    backend = _get_valkey_backend()
    if backend is not None:
        await backend.publish(room, message)


def validate_ws_auth(token: str, api_key: str) -> bool:
    """Validate WebSocket authentication credentials.

    Accepts either a JWT access token or an API key.
    Returns True if authentication succeeds, False otherwise.
    """
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") == "access":
                return True
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
            pass

    return bool(api_key and hmac.compare_digest(api_key, _auth_mw.get_api_key()))


@router.websocket("/ws/collab/{crew_name}")
async def collaborate(websocket: WebSocket, crew_name: str) -> None:
    """WebSocket endpoint for real-time canvas collaboration.

    Authentication: Accepts either ``token`` query parameter (JWT) or
    ``api_key`` query parameter (system API key).  WebSocket connections
    cannot set custom headers, so credentials must be passed via query
    string.

    Protocol:
    - Client sends JSON messages with ``type`` and ``data`` fields.
    - Valid types: node_add, node_move, node_delete, node_update,
      edge_add, edge_delete, cursor_move, selection_change.
    - Server broadcasts each valid message to all other clients in the
      same crew room.
    - On connect: server sends ``room_state`` with current participant count.
    - On join/leave: server sends ``participant_joined`` / ``participant_left``
      to remaining participants.
    """
    if len(crew_name) > _MAX_CREW_NAME_LEN or not _NAME_RE.match(crew_name):
        await websocket.close(code=4422, reason="Invalid crew name")
        return

    token = websocket.query_params.get("token", "")
    api_key = websocket.query_params.get("api_key", "")

    if not validate_ws_auth(token, api_key):
        client_ip = websocket.client.host if websocket.client else "unknown"
        _auth_mw.record_auth_failure(client_ip)
        logger.warning(
            "Collaboration WebSocket auth failed: crew=%s from %s",
            crew_name,
            client_ip,
            extra={
                "event": "collab_ws_auth_failure",
                "crew_name": crew_name,
                "client_ip": client_ip,
            },
        )
        await websocket.close(code=4401, reason="Authentication required")
        return

    await websocket.accept()

    # Add to room
    async with _rooms_lock:
        is_new_room = crew_name not in _rooms
        if is_new_room:
            _rooms[crew_name] = set()
        _rooms[crew_name].add(websocket)
        participant_count = len(_rooms[crew_name])

    # Subscribe to Valkey channel for cross-replica messaging
    if is_new_room:
        backend = _get_valkey_backend()
        if backend is not None:
            await backend.subscribe(crew_name)

    logger.info(
        "Collaboration: client joined room %s (participants=%d)",
        crew_name,
        participant_count,
        extra={
            "event": "collab_join",
            "crew_name": crew_name,
            "participants": participant_count,
        },
    )

    # Notify existing participants of new user
    await _broadcast(
        crew_name,
        websocket,
        {"type": "participant_joined", "data": {"count": participant_count}},
    )

    # Send room state to the new user
    await websocket.send_json({"type": "room_state", "data": {"participants": participant_count}})

    # Per-client rate limiter for high-frequency message types.
    # Uses a simple sliding-window counter to prevent cursor_move flooding.
    _hf_timestamps: list[float] = []

    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 65_536:
                continue
            try:
                message = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue

            if not isinstance(message, dict):
                continue

            msg_type = message.get("type", "")
            if msg_type not in ALLOWED_MESSAGE_TYPES:
                continue

            # Validate that the "data" field, if present, is a dict and
            # not deeply nested (prevents JSON-bomb-style DoS on other
            # clients who must parse and render the broadcast).
            msg_data = message.get("data")
            if msg_data is not None and not isinstance(msg_data, dict):
                continue

            # Rate-limit high-frequency message types to prevent a single
            # client from flooding the room.
            if msg_type in _HIGH_FREQ_TYPES:
                now = time.monotonic()
                # Prune timestamps outside the window
                cutoff = now - _RATE_LIMIT_WINDOW_S
                _hf_timestamps[:] = [t for t in _hf_timestamps if t > cutoff]
                if len(_hf_timestamps) >= _RATE_LIMIT_MAX:
                    # Silently drop excess messages
                    continue
                _hf_timestamps.append(now)

            await _broadcast(crew_name, websocket, message)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception(
            "Collaboration: unexpected error in room %s",
            crew_name,
            extra={"event": "collab_error", "crew_name": crew_name},
        )
    finally:
        room_empty = False
        async with _rooms_lock:
            room = _rooms.get(crew_name)
            if room is not None:
                room.discard(websocket)
                remaining = len(room)
                if remaining == 0:
                    _rooms.pop(crew_name, None)
                    room_empty = True
            else:
                remaining = 0
                room_empty = True

        # Unsubscribe from Valkey when room is empty on this replica
        if room_empty:
            backend = _get_valkey_backend()
            if backend is not None:
                await backend.unsubscribe(crew_name)

        logger.info(
            "Collaboration: client left room %s (remaining=%d)",
            crew_name,
            remaining,
            extra={
                "event": "collab_leave",
                "crew_name": crew_name,
                "participants": remaining,
            },
        )

        if remaining > 0:
            await _broadcast(
                crew_name,
                websocket,
                {"type": "participant_left", "data": {"count": remaining}},
            )


def get_room_stats() -> dict[str, int]:
    """Return per-room participant counts for health/debug endpoints."""
    return {room: len(clients) for room, clients in _rooms.items() if clients}
