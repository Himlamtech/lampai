"""WebSocket connection manager for XiaoZhi protocol."""
import uuid
import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from fastapi import WebSocket, WebSocketDisconnect

from app.core.logging import get_logger

logger = get_logger("websocket_manager")


class SessionState(str, Enum):
    CONNECTED = "connected"
    WAITING_HELLO = "waiting_hello"
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


@dataclass
class Session:
    session_id: str
    device_id: str
    websocket: WebSocket
    state: SessionState = SessionState.CONNECTED
    mode: str | None = None
    protocol_version: int = 1
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    audio_buffer: bytearray = field(default_factory=bytearray)

    def touch(self):
        self.last_activity_at = datetime.now(timezone.utc)


class WebSocketManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}  # session_id -> Session
        self._device_sessions: dict[str, str] = {}  # device_id -> session_id

    def generate_session_id(self) -> str:
        return str(uuid.uuid4())

    async def register_session(self, session: Session) -> None:
        self._sessions[session.session_id] = session
        self._device_sessions[session.device_id] = session.session_id
        logger.info(
            "session_registered",
            session_id=session.session_id,
            device_id=session.device_id,
        )

    async def remove_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            self._device_sessions.pop(session.device_id, None)
            logger.info(
                "session_removed",
                session_id=session_id,
                device_id=session.device_id,
            )

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_session_by_device(self, device_id: str) -> Session | None:
        session_id = self._device_sessions.get(device_id)
        if session_id:
            return self._sessions.get(session_id)
        return None

    def get_active_session_count(self) -> int:
        return len(self._sessions)

    def get_all_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    async def transition(self, session_id: str, new_state: SessionState) -> None:
        session = self._sessions.get(session_id)
        if session:
            old_state = session.state
            session.state = new_state
            session.touch()
            logger.debug(
                "session_state_transition",
                session_id=session_id,
                device_id=session.device_id,
                old_state=old_state.value,
                new_state=new_state.value,
            )

    async def send_json(self, session_id: str, message: dict) -> bool:
        session = self._sessions.get(session_id)
        if session:
            try:
                await session.websocket.send_json(message)
                session.touch()
                return True
            except Exception as e:
                logger.error("send_json_failed", session_id=session_id, error=str(e))
                return False
        return False

    async def send_binary(self, session_id: str, data: bytes) -> bool:
        session = self._sessions.get(session_id)
        if session:
            try:
                await session.websocket.send_bytes(data)
                session.touch()
                return True
            except Exception as e:
                logger.error("send_binary_failed", session_id=session_id, error=str(e))
                return False
        return False

    def is_device_online(self, device_id: str) -> bool:
        return device_id in self._device_sessions


ws_manager = WebSocketManager()
