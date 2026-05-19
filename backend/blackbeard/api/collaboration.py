"""WebSocket endpoint for real-time canvas collaboration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

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
# Suitable for single-process MVP; for multi-process deployments, replace
# with Redis pub/sub or similar.
_rooms: dict[str, set[WebSocket]] = {}
_rooms_lock = asyncio.Lock()


async def _broadcast(
    room: str,
    sender: WebSocket,
    message: dict[str, Any],
) -> None:
    """Send message to all participants in a room except the sender.

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


@router.websocket("/ws/collab/{crew_name}")
async def collaborate(websocket: WebSocket, crew_name: str) -> None:
    """WebSocket endpoint for real-time canvas collaboration.

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
    await websocket.accept()

    # Add to room
    async with _rooms_lock:
        if crew_name not in _rooms:
            _rooms[crew_name] = set()
        _rooms[crew_name].add(websocket)
        participant_count = len(_rooms[crew_name])

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
    await websocket.send_json(
        {"type": "room_state", "data": {"participants": participant_count}}
    )

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
        async with _rooms_lock:
            room = _rooms.get(crew_name)
            if room is not None:
                room.discard(websocket)
                remaining = len(room)
                if remaining == 0:
                    _rooms.pop(crew_name, None)
            else:
                remaining = 0

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
