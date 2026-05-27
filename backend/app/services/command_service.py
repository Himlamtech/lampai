"""Command dispatcher service."""
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.commands import DeviceCommand, CommandAck, CommandStatus, CommandType
from app.domain.intents import IntentType, ParsedIntent
from app.domain.device_state import DeviceStatus
from app.repositories.command_repository import CommandRepository
from app.services.device_service import DeviceService
from app.infra.websocket_manager import ws_manager
from app.core.errors import DeviceOfflineError, CommandTimeoutError
from app.core.logging import get_logger

logger = get_logger("command_service")


def _generate_command_id() -> str:
    return f"cmd_{uuid.uuid4().hex[:12]}"


def _intent_to_command_type(intent: IntentType) -> str:
    """Map intent type to command type."""
    mapping = {
        IntentType.TURN_ON_LIGHT: CommandType.TURN_ON_LIGHT.value,
        IntentType.TURN_OFF_LIGHT: CommandType.TURN_OFF_LIGHT.value,
        IntentType.SET_BRIGHTNESS: CommandType.SET_BRIGHTNESS.value,
        IntentType.INCREASE_BRIGHTNESS: CommandType.SET_BRIGHTNESS.value,
        IntentType.DECREASE_BRIGHTNESS: CommandType.SET_BRIGHTNESS.value,
        IntentType.CHANGE_LIGHT_MODE: CommandType.CHANGE_LIGHT_MODE.value,
        IntentType.PLAY_MUSIC: CommandType.PLAY_MUSIC.value,
        IntentType.STOP_MUSIC: CommandType.STOP_MUSIC.value,
    }
    return mapping.get(intent, intent.value)


class CommandDispatcher:
    def __init__(self, session: AsyncSession):
        self.repo = CommandRepository(session)
        self.device_service = DeviceService(session)

    async def dispatch(self, device_id: str, intent: ParsedIntent) -> DeviceCommand:
        """Build and send a command to the device."""
        # Check if device is online (has active WebSocket)
        if not ws_manager.is_device_online(device_id):
            # Check DB state as fallback
            state = await self.device_service.get_state(device_id)
            if state is None or state.status == DeviceStatus.OFFLINE:
                command_id = _generate_command_id()
                await self.repo.create(
                    command_id=command_id,
                    device_id=device_id,
                    command_type=_intent_to_command_type(intent.intent),
                    payload=intent.params,
                )
                await self.repo.update_status(command_id, CommandStatus.FAILED, "device_offline")
                logger.warning(
                    "command_dispatch_failed",
                    device_id=device_id,
                    reason="device_offline",
                    intent=intent.intent.value,
                )
                raise DeviceOfflineError(device_id)

        # Build payload based on intent
        payload = await self._build_payload(device_id, intent)

        # Build command
        command_id = _generate_command_id()
        command = DeviceCommand(
            commandId=command_id,
            deviceId=device_id,
            type=_intent_to_command_type(intent.intent),
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Persist command
        await self.repo.create(
            command_id=command_id,
            device_id=device_id,
            command_type=command.type,
            payload=payload,
        )

        # Send via WebSocket
        session = ws_manager.get_session_by_device(device_id)
        if session:
            success = await ws_manager.send_json(session.session_id, command.model_dump())
            if success:
                await self.repo.update_status(command_id, CommandStatus.SENT)
                logger.info(
                    "command_sent",
                    command_id=command_id,
                    device_id=device_id,
                    type=command.type,
                )
            else:
                await self.repo.update_status(command_id, CommandStatus.FAILED, "send_failed")
                logger.error("command_send_failed", command_id=command_id, device_id=device_id)
        else:
            await self.repo.update_status(command_id, CommandStatus.FAILED, "no_active_session")

        return command

    async def handle_ack(self, ack: CommandAck) -> None:
        """Process a command acknowledgement from device."""
        if ack.status == "SUCCESS":
            await self.repo.update_status(ack.commandId, CommandStatus.SUCCESS)
            # Update device state from ack
            if ack.state:
                state_updates = {}
                if "lightPower" in ack.state:
                    state_updates["light_power"] = ack.state["lightPower"]
                if "brightness" in ack.state:
                    state_updates["brightness"] = ack.state["brightness"]
                if "mode" in ack.state:
                    state_updates["mode"] = ack.state["mode"]
                if "isPlayingMusic" in ack.state:
                    state_updates["is_playing_music"] = ack.state["isPlayingMusic"]
                if "volume" in ack.state:
                    state_updates["volume"] = ack.state["volume"]
                if state_updates:
                    await self.device_service.update_state(ack.deviceId, state_updates)
            logger.info("command_ack_success", command_id=ack.commandId, device_id=ack.deviceId)
        else:
            await self.repo.update_status(
                ack.commandId, CommandStatus.FAILED, ack.error or "device_rejected"
            )
            logger.warning(
                "command_ack_failed",
                command_id=ack.commandId,
                device_id=ack.deviceId,
                error=ack.error,
            )

    async def _build_payload(self, device_id: str, intent: ParsedIntent) -> dict:
        """Build command payload based on intent type and current device state."""
        if intent.intent == IntentType.SET_BRIGHTNESS:
            return {"brightness": intent.params.get("brightness", 50)}

        elif intent.intent == IntentType.INCREASE_BRIGHTNESS:
            state = await self.device_service.get_state(device_id)
            current = state.brightness if state else 50
            new_brightness = min(current + 20, 100)
            return {"brightness": new_brightness}

        elif intent.intent == IntentType.DECREASE_BRIGHTNESS:
            state = await self.device_service.get_state(device_id)
            current = state.brightness if state else 50
            new_brightness = max(current - 20, 0)
            return {"brightness": new_brightness}

        elif intent.intent == IntentType.CHANGE_LIGHT_MODE:
            return {"mode": intent.params.get("mode", "NORMAL")}

        elif intent.intent == IntentType.PLAY_MUSIC:
            return {
                "trackId": intent.params.get("track_id", ""),
                "musicType": intent.params.get("music_type", "SLEEP"),
                "durationSeconds": intent.params.get("duration_seconds", 0),
            }

        return {}
