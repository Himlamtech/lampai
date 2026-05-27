"""WebSocket endpoint implementing XiaoZhi protocol."""
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.logging import get_logger
from app.infra.websocket_manager import ws_manager, Session, SessionState
from app.schemas.device import HelloMessage, AudioParams, ServerHelloResponse
from app.domain.commands import CommandAck

logger = get_logger("websocket")

router = APIRouter()


def _validate_headers(websocket: WebSocket) -> tuple[str, int, str, str] | None:
    """Validate WebSocket connection headers. Returns (token, version, device_id, client_id) or None."""
    headers = dict(websocket.headers)
    auth = headers.get("authorization", "")
    version_str = headers.get("protocol-version", "")
    device_id = headers.get("device-id", "")
    client_id = headers.get("client-id", "")

    if not auth or not device_id or not client_id:
        return None

    # Validate Bearer token
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if token != settings.device_auth_token:
        return None

    # Parse version
    try:
        version = int(version_str) if version_str else 1
    except ValueError:
        version = 1

    return token, version, device_id, client_id


async def _wait_for_hello(websocket: WebSocket, timeout: int) -> HelloMessage | None:
    """Wait for device hello message within timeout."""
    try:
        data = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=timeout,
        )
        msg = json.loads(data)
        if msg.get("type") != "hello":
            return None
        return HelloMessage(**msg)
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
        logger.warning("hello_wait_failed", error=str(e))
        return None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """XiaoZhi protocol WebSocket endpoint."""
    # Validate headers before accepting
    header_result = _validate_headers(websocket)
    if header_result is None:
        await websocket.close(code=4001, reason="Invalid or missing authentication headers")
        return

    token, version, device_id, client_id = header_result

    # Accept connection
    await websocket.accept()
    logger.info("websocket_connected", device_id=device_id, protocol_version=version)

    # Wait for hello message
    hello = await _wait_for_hello(websocket, settings.hello_timeout_seconds)
    if hello is None:
        logger.warning("hello_timeout", device_id=device_id)
        await websocket.close(code=4002, reason="Hello timeout or invalid hello message")
        return

    # Validate protocol version
    if hello.version not in (1, 2, 3):
        error_msg = json.dumps({
            "type": "error",
            "message": f"Unsupported protocol version {hello.version}. Supported: 1, 2, 3",
        })
        await websocket.send_text(error_msg)
        await websocket.close(code=4003, reason="Unsupported protocol version")
        return

    # Create session
    session_id = ws_manager.generate_session_id()
    session = Session(
        session_id=session_id,
        device_id=device_id,
        websocket=websocket,
        state=SessionState.IDLE,
        protocol_version=hello.version,
    )
    await ws_manager.register_session(session)

    # Send server hello
    server_hello = ServerHelloResponse(
        session_id=session_id,
        audio_params=AudioParams(sample_rate=24000),
    )
    await websocket.send_text(server_hello.model_dump_json())
    logger.info("hello_handshake_complete", session_id=session_id, device_id=device_id)

    # Main message loop
    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.receive":
                if "text" in message:
                    await _handle_text_message(session, message["text"])
                elif "bytes" in message:
                    await _handle_binary_message(session, message["bytes"])

            elif message["type"] == "websocket.disconnect":
                break

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=session_id, device_id=device_id)
    except Exception as e:
        logger.error("websocket_error", session_id=session_id, device_id=device_id, error=str(e))
    finally:
        await ws_manager.remove_session(session_id)
        logger.info("session_cleanup_complete", session_id=session_id, device_id=device_id)


async def _handle_text_message(session: Session, text: str) -> None:
    """Handle incoming JSON text message."""
    try:
        msg = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("malformed_json", session_id=session.session_id, raw=text[:100])
        return

    msg_type = msg.get("type")
    if not msg_type:
        logger.warning("missing_message_type", session_id=session.session_id)
        return

    if msg_type == "listen":
        await _handle_listen_message(session, msg)
    elif msg_type == "abort":
        await _handle_abort_message(session, msg)
    elif msg_type == "mcp":
        await _handle_mcp_message(session, msg)
    elif msg_type == "COMMAND_ACK":
        # Handle command acknowledgement (messageType field)
        pass
    else:
        # Check if it's a command ack by messageType field
        if msg.get("messageType") == "COMMAND_ACK":
            await _handle_command_ack(session, msg)
        else:
            logger.debug("unknown_message_type", session_id=session.session_id, type=msg_type)


async def _handle_listen_message(session: Session, msg: dict) -> None:
    """Handle listen state messages."""
    state = msg.get("state")
    mode = msg.get("mode")

    if state == "start":
        session.audio_buffer = bytearray()
        session.mode = mode
        await ws_manager.transition(session.session_id, SessionState.LISTENING)
        logger.info(
            "listening_started",
            session_id=session.session_id,
            device_id=session.device_id,
            mode=mode,
        )

    elif state == "stop":
        await ws_manager.transition(session.session_id, SessionState.PROCESSING)
        logger.info(
            "listening_stopped",
            session_id=session.session_id,
            device_id=session.device_id,
            buffer_size=len(session.audio_buffer),
        )
        # Voice pipeline processing will be connected in Task 19
        # For now, just transition back to idle
        await ws_manager.transition(session.session_id, SessionState.IDLE)

    elif state == "detect":
        # Wake word detected
        wake_text = msg.get("text", "")
        logger.info(
            "wake_word_detected",
            session_id=session.session_id,
            device_id=session.device_id,
            text=wake_text,
        )


async def _handle_abort_message(session: Session, msg: dict) -> None:
    """Handle abort message — cancel current operation."""
    reason = msg.get("reason", "user_abort")
    session.audio_buffer = bytearray()
    await ws_manager.transition(session.session_id, SessionState.IDLE)
    logger.info(
        "session_aborted",
        session_id=session.session_id,
        device_id=session.device_id,
        reason=reason,
    )


async def _handle_mcp_message(session: Session, msg: dict) -> None:
    """Handle MCP (Model Context Protocol) messages."""
    payload = msg.get("payload", {})
    logger.info(
        "mcp_message_received",
        session_id=session.session_id,
        device_id=session.device_id,
        method=payload.get("method"),
    )
    # MCP handling will be implemented later


async def _handle_command_ack(session: Session, msg: dict) -> None:
    """Handle command acknowledgement from device."""
    try:
        ack = CommandAck(**msg)
        logger.info(
            "command_ack_received",
            session_id=session.session_id,
            command_id=ack.commandId,
            status=ack.status,
        )
        # Command dispatcher will process this in the voice pipeline integration
    except Exception as e:
        logger.warning("invalid_command_ack", session_id=session.session_id, error=str(e))


async def _handle_binary_message(session: Session, data: bytes) -> None:
    """Handle incoming binary audio frames."""
    if session.state != SessionState.LISTENING:
        # Discard binary frames when not in listening state
        return

    session.audio_buffer.extend(data)
    session.touch()

    # Check max buffer size (60 seconds * 16000 Hz * 2 bytes per sample ≈ 1.92MB for raw PCM)
    # For Opus at ~32kbps, 60s ≈ 240KB
    max_buffer_bytes = settings.max_audio_buffer_seconds * 32000 // 8  # rough Opus estimate
    if len(session.audio_buffer) >= max_buffer_bytes:
        logger.warning(
            "audio_buffer_max_reached",
            session_id=session.session_id,
            device_id=session.device_id,
            buffer_size=len(session.audio_buffer),
        )
        await ws_manager.transition(session.session_id, SessionState.PROCESSING)
        # Will trigger STT processing when voice pipeline is connected
        await ws_manager.transition(session.session_id, SessionState.IDLE)
