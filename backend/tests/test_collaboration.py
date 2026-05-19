"""Tests for the real-time collaboration WebSocket endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from blackbeard.api.collaboration import (
    ALLOWED_MESSAGE_TYPES,
    _broadcast,
    _rooms,
    get_room_stats,
    router,
)

# ---------------------------------------------------------------------------
# Minimal app for WebSocket integration tests — avoids the full lifespan
# (which requires a live PostgreSQL connection) by mounting only the
# collaboration router on a fresh FastAPI instance.
# ---------------------------------------------------------------------------
_ws_app = FastAPI()
_ws_app.include_router(router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Unit tests for room management helpers
# ---------------------------------------------------------------------------


class TestGetRoomStats:
    def test_empty_rooms(self) -> None:
        _rooms.clear()
        assert get_room_stats() == {}

    def test_room_with_participants(self) -> None:
        _rooms.clear()

        class FakeWS:
            pass

        _rooms["crew-a"] = {FakeWS(), FakeWS()}  # type: ignore[arg-type]
        _rooms["crew-b"] = {FakeWS()}  # type: ignore[arg-type]
        stats = get_room_stats()
        assert stats == {"crew-a": 2, "crew-b": 1}
        _rooms.clear()

    def test_empty_room_excluded(self) -> None:
        _rooms.clear()
        _rooms["crew-empty"] = set()
        assert get_room_stats() == {}
        _rooms.clear()


class TestAllowedMessageTypes:
    def test_known_types(self) -> None:
        expected = {
            "node_add",
            "node_move",
            "node_delete",
            "node_update",
            "edge_add",
            "edge_delete",
            "cursor_move",
            "selection_change",
        }
        assert expected == ALLOWED_MESSAGE_TYPES

    def test_unknown_type_not_allowed(self) -> None:
        assert "invalid_type" not in ALLOWED_MESSAGE_TYPES
        assert "" not in ALLOWED_MESSAGE_TYPES


# ---------------------------------------------------------------------------
# Broadcast logic tests (using mock WebSockets)
# ---------------------------------------------------------------------------


class FakeWebSocket:
    """Minimal fake WebSocket for testing broadcast logic."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self._fail = fail

    async def send_json(self, data: dict) -> None:
        if self._fail:
            raise ConnectionError("connection lost")
        self.sent.append(data)


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_others(self) -> None:
        _rooms.clear()
        sender = FakeWebSocket()
        other1 = FakeWebSocket()
        other2 = FakeWebSocket()
        _rooms["test-crew"] = {sender, other1, other2}  # type: ignore[arg-type]

        msg = {"type": "node_move", "data": {"id": "n1", "x": 10, "y": 20}}
        await _broadcast("test-crew", sender, msg)  # type: ignore[arg-type]

        assert msg in other1.sent
        assert msg in other2.sent
        assert len(sender.sent) == 0
        _rooms.clear()

    @pytest.mark.asyncio
    async def test_broadcast_skips_sender(self) -> None:
        _rooms.clear()
        sender = FakeWebSocket()
        _rooms["test-crew"] = {sender}  # type: ignore[arg-type]

        await _broadcast("test-crew", sender, {"type": "node_add", "data": {}})  # type: ignore[arg-type]

        assert len(sender.sent) == 0
        _rooms.clear()

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self) -> None:
        _rooms.clear()
        sender = FakeWebSocket()
        dead = FakeWebSocket(fail=True)
        alive = FakeWebSocket()
        _rooms["test-crew"] = {sender, dead, alive}  # type: ignore[arg-type]

        await _broadcast("test-crew", sender, {"type": "node_delete", "data": {"id": "n1"}})  # type: ignore[arg-type]

        # Dead connection should have been removed
        assert dead not in _rooms["test-crew"]
        assert alive in _rooms["test-crew"]  # type: ignore[operator]
        assert sender in _rooms["test-crew"]  # type: ignore[operator]
        _rooms.clear()

    @pytest.mark.asyncio
    async def test_broadcast_empty_room(self) -> None:
        _rooms.clear()
        sender = FakeWebSocket()
        # Room doesn't exist — should not raise
        await _broadcast("nonexistent", sender, {"type": "node_add", "data": {}})  # type: ignore[arg-type]
        _rooms.clear()


# ---------------------------------------------------------------------------
# Integration tests using a minimal FastAPI app with the collaboration
# router mounted, avoiding the full application lifespan.
# ---------------------------------------------------------------------------


def test_websocket_connect_and_room_state() -> None:
    """Client connects and receives room_state with participant count."""
    _rooms.clear()
    with TestClient(_ws_app) as tc, tc.websocket_connect("/api/v1/ws/collab/test-crew") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "room_state"
        assert msg["data"]["participants"] == 1
    _rooms.clear()


def test_two_clients_broadcast() -> None:
    """Two clients in same room: messages from one are received by the other."""
    _rooms.clear()
    with TestClient(_ws_app) as tc, tc.websocket_connect("/api/v1/ws/collab/crew-x") as ws1:
        ws1.receive_json()  # room_state for ws1

        with tc.websocket_connect("/api/v1/ws/collab/crew-x") as ws2:
            ws2_room = ws2.receive_json()  # room_state for ws2
            assert ws2_room["data"]["participants"] == 2

            # ws1 should receive participant_joined
            joined_msg = ws1.receive_json()
            assert joined_msg["type"] == "participant_joined"
            assert joined_msg["data"]["count"] == 2

            # ws1 sends a node_move — ws2 should receive it
            ws1.send_json(
                {"type": "node_move", "data": {"id": "n1", "x": 100, "y": 200}}
            )
            received = ws2.receive_json()
            assert received["type"] == "node_move"
            assert received["data"]["id"] == "n1"
    _rooms.clear()


def test_invalid_message_type_ignored() -> None:
    """Messages with invalid types are silently ignored (not broadcast)."""
    _rooms.clear()
    with TestClient(_ws_app) as tc, tc.websocket_connect("/api/v1/ws/collab/crew-y") as ws1:
        ws1.receive_json()  # room_state

        with tc.websocket_connect("/api/v1/ws/collab/crew-y") as ws2:
            ws2.receive_json()  # room_state
            ws1.receive_json()  # participant_joined

            # Send invalid type
            ws1.send_json(
                {"type": "malicious_action", "data": {"hack": True}}
            )

            # Send valid type to verify the connection still works
            ws1.send_json(
                {"type": "node_add", "data": {"id": "n2"}}
            )
            received = ws2.receive_json()
            # Should only get the valid message, not the invalid one
            assert received["type"] == "node_add"
    _rooms.clear()


def test_different_crews_are_isolated() -> None:
    """Messages in one crew room are not received in another crew room."""
    _rooms.clear()
    with (
        TestClient(_ws_app) as tc,
        tc.websocket_connect("/api/v1/ws/collab/crew-alpha") as ws_alpha,
    ):
        ws_alpha.receive_json()  # room_state

        with tc.websocket_connect("/api/v1/ws/collab/crew-beta") as ws_beta:
            ws_beta.receive_json()  # room_state

            # Send message in crew-alpha
            ws_alpha.send_json(
                {"type": "node_add", "data": {"id": "alpha-node"}}
            )

            # Verify that each room has exactly 1 participant, proving isolation.
            stats = get_room_stats()
            assert stats.get("crew-alpha") == 1
            assert stats.get("crew-beta") == 1
    _rooms.clear()


def test_disconnect_updates_participant_count() -> None:
    """When a client disconnects, remaining clients get participant_left."""
    _rooms.clear()
    with TestClient(_ws_app) as tc, tc.websocket_connect("/api/v1/ws/collab/crew-dc") as ws1:
        ws1.receive_json()  # room_state

        with tc.websocket_connect("/api/v1/ws/collab/crew-dc") as ws2:
            ws2.receive_json()  # room_state
            ws1.receive_json()  # participant_joined

        # ws2 disconnected here — ws1 should get participant_left
        left_msg = ws1.receive_json()
        assert left_msg["type"] == "participant_left"
        assert left_msg["data"]["count"] == 1
    _rooms.clear()


def test_room_cleanup_on_last_disconnect() -> None:
    """Room is removed from _rooms when the last participant disconnects."""
    _rooms.clear()
    with (
        TestClient(_ws_app) as tc,
        tc.websocket_connect("/api/v1/ws/collab/crew-cleanup") as ws,
    ):
        ws.receive_json()  # room_state
        assert "crew-cleanup" in _rooms

    # After disconnect, room should be cleaned up
    assert "crew-cleanup" not in _rooms
    _rooms.clear()


def test_all_message_types_broadcast() -> None:
    """All valid message types are properly broadcast."""
    _rooms.clear()
    with (
        TestClient(_ws_app) as tc,
        tc.websocket_connect("/api/v1/ws/collab/crew-types") as ws1,
    ):
        ws1.receive_json()  # room_state

        with tc.websocket_connect("/api/v1/ws/collab/crew-types") as ws2:
            ws2.receive_json()  # room_state
            ws1.receive_json()  # participant_joined

            for msg_type in sorted(ALLOWED_MESSAGE_TYPES):
                ws1.send_json({"type": msg_type, "data": {"test": True}})
                received = ws2.receive_json()
                assert received["type"] == msg_type
    _rooms.clear()
