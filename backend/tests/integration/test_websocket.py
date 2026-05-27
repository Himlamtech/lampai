"""Integration tests for WebSocket protocol handshake."""
import pytest
import json
import asyncio
from unittest.mock import patch, AsyncMock

from app.infra.websocket_manager import ws_manager, Session, SessionState, WebSocketManager


class TestWebSocketManager:
    @pytest.fixture
    def manager(self):
        return WebSocketManager()

    def test_generate_session_id(self, manager):
        sid1 = manager.generate_session_id()
        sid2 = manager.generate_session_id()
        assert sid1 != sid2
        assert len(sid1) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_register_and_get_session(self, manager):
        mock_ws = AsyncMock()
        session = Session(
            session_id="test-session-1",
            device_id="AA:BB:CC:DD:EE:FF",
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await manager.register_session(session)

        assert manager.get_session("test-session-1") is session
        assert manager.get_session_by_device("AA:BB:CC:DD:EE:FF") is session
        assert manager.get_active_session_count() == 1

    @pytest.mark.asyncio
    async def test_remove_session(self, manager):
        mock_ws = AsyncMock()
        session = Session(
            session_id="test-session-2",
            device_id="AA:BB:CC:DD:EE:01",
            websocket=mock_ws,
        )
        await manager.register_session(session)
        await manager.remove_session("test-session-2")

        assert manager.get_session("test-session-2") is None
        assert manager.get_session_by_device("AA:BB:CC:DD:EE:01") is None
        assert manager.get_active_session_count() == 0

    @pytest.mark.asyncio
    async def test_transition_state(self, manager):
        mock_ws = AsyncMock()
        session = Session(
            session_id="test-session-3",
            device_id="AA:BB:CC:DD:EE:02",
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await manager.register_session(session)
        await manager.transition("test-session-3", SessionState.LISTENING)

        assert session.state == SessionState.LISTENING

    @pytest.mark.asyncio
    async def test_send_json(self, manager):
        mock_ws = AsyncMock()
        session = Session(
            session_id="test-session-4",
            device_id="AA:BB:CC:DD:EE:03",
            websocket=mock_ws,
        )
        await manager.register_session(session)

        result = await manager.send_json("test-session-4", {"type": "test"})
        assert result is True
        mock_ws.send_json.assert_called_once_with({"type": "test"})

    @pytest.mark.asyncio
    async def test_send_binary(self, manager):
        mock_ws = AsyncMock()
        session = Session(
            session_id="test-session-5",
            device_id="AA:BB:CC:DD:EE:04",
            websocket=mock_ws,
        )
        await manager.register_session(session)

        data = b"\x00\x01\x02\x03"
        result = await manager.send_binary("test-session-5", data)
        assert result is True
        mock_ws.send_bytes.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_is_device_online(self, manager):
        mock_ws = AsyncMock()
        session = Session(
            session_id="test-session-6",
            device_id="AA:BB:CC:DD:EE:05",
            websocket=mock_ws,
        )
        await manager.register_session(session)

        assert manager.is_device_online("AA:BB:CC:DD:EE:05") is True
        assert manager.is_device_online("AA:BB:CC:DD:EE:99") is False

    @pytest.mark.asyncio
    async def test_send_json_to_nonexistent_session(self, manager):
        result = await manager.send_json("nonexistent", {"type": "test"})
        assert result is False


class TestSessionState:
    def test_all_states_defined(self):
        expected = {"connected", "waiting_hello", "idle", "listening", "processing", "speaking"}
        actual = {s.value for s in SessionState}
        assert actual == expected

    def test_session_touch_updates_timestamp(self):
        from datetime import datetime, timezone, timedelta
        mock_ws = AsyncMock()
        session = Session(
            session_id="test",
            device_id="AA:BB:CC:DD:EE:FF",
            websocket=mock_ws,
        )
        old_time = session.last_activity_at
        import time
        time.sleep(0.01)
        session.touch()
        assert session.last_activity_at > old_time
