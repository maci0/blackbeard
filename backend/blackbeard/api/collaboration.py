"""WebSocket endpoint for real-time canvas collaboration."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from typing import TYPE_CHECKING, Any

import jwt as pyjwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from blackbeard.api.middleware import _EXPECTED_API_KEY, _record_auth_failure
from blackbeard.auth.jwt import decode_token

if TYPE_CHECKING:
    pass

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
    except (ImportError, Exception):
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


def _validate_ws_auth(token: str, api_key: str) -> bool:
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

    return bool(api_key and hmac.compare_digest(api_key, _EXPECTED_API_KEY))


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
    token = websocket.query_params.get("token", "")
    api_key = websocket.query_params.get("api_key", "")

    if not _validate_ws_auth(token, api_key):
        client_ip = websocket.client.host if websocket.client else "unknown"
        _record_auth_failure(client_ip)
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

    try:
        while True:
            message = await websocket.receive_json()

            # Validate message structure
            if not isinstance(message, dict):
                continue

            msg_type = message.get("type", "")
            if msg_type not in ALLOWED_MESSAGE_TYPES:
                continue

            # Broadcast to all other clients in the room
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
