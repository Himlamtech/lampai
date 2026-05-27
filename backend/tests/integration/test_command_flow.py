"""Integration tests for command dispatch flow."""
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.infra.database import Base
from app.infra.models import DeviceModel, CommandModel  # noqa
from app.core.config import settings
from app.services.device_service import DeviceService
from app.services.command_service import CommandDispatcher
from app.domain.intents import IntentType, ParsedIntent
from app.domain.commands import CommandAck, CommandStatus
from app.core.errors import DeviceOfflineError


@pytest.fixture
async def engine():
    eng = create_async_engine(settings.database_url, echo=False, pool_size=5)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture
async def device_service(session):
    return DeviceService(session)


@pytest.fixture
async def command_dispatcher(session):
    return CommandDispatcher(session)


@pytest.fixture
async def registered_device(device_service):
    """Register a device for testing."""
    await device_service.register("AA:BB:CC:DD:EE:11")
    return "AA:BB:CC:DD:EE:11"


class TestCommandDispatchOffline:
    @pytest.mark.asyncio
    async def test_dispatch_to_offline_device_raises(self, command_dispatcher, registered_device):
        """Dispatching to an offline device should raise DeviceOfflineError."""
        intent = ParsedIntent(intent=IntentType.TURN_ON_LIGHT)
        with pytest.raises(DeviceOfflineError):
            await command_dispatcher.dispatch(registered_device, intent)

    @pytest.mark.asyncio
    async def test_offline_command_stored_as_failed(self, command_dispatcher, registered_device, session):
        """Failed commands should be stored in DB with FAILED status."""
        intent = ParsedIntent(intent=IntentType.TURN_ON_LIGHT)
        try:
            await command_dispatcher.dispatch(registered_device, intent)
        except DeviceOfflineError:
            pass

        # Check command was stored
        from sqlalchemy import select
        from app.infra.models import CommandModel
        result = await session.execute(
            select(CommandModel).where(CommandModel.device_id == registered_device)
        )
        commands = list(result.scalars().all())
        assert len(commands) == 1
        assert commands[0].status == "FAILED"
        assert commands[0].failure_reason == "device_offline"


class TestCommandDispatchOnline:
    @pytest.mark.asyncio
    async def test_dispatch_turn_on_light(self, command_dispatcher, registered_device):
        """Dispatch TURN_ON_LIGHT to an online device."""
        from app.infra.websocket_manager import ws_manager, Session, SessionState

        # Simulate device being online
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()
        test_session = Session(
            session_id="test-session",
            device_id=registered_device,
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await ws_manager.register_session(test_session)

        try:
            intent = ParsedIntent(intent=IntentType.TURN_ON_LIGHT)
            command = await command_dispatcher.dispatch(registered_device, intent)

            assert command.type == "TURN_ON_LIGHT"
            assert command.deviceId == registered_device
            assert command.messageType == "COMMAND"
            assert command.commandId.startswith("cmd_")
            assert command.payload == {}
            mock_ws.send_json.assert_called_once()
        finally:
            await ws_manager.remove_session("test-session")

    @pytest.mark.asyncio
    async def test_dispatch_set_brightness(self, command_dispatcher, registered_device):
        """Dispatch SET_BRIGHTNESS with value."""
        from app.infra.websocket_manager import ws_manager, Session, SessionState

        mock_ws = AsyncMock()
        test_session = Session(
            session_id="test-session-2",
            device_id=registered_device,
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await ws_manager.register_session(test_session)

        try:
            intent = ParsedIntent(
                intent=IntentType.SET_BRIGHTNESS,
                params={"brightness": 75},
            )
            command = await command_dispatcher.dispatch(registered_device, intent)

            assert command.type == "SET_BRIGHTNESS"
            assert command.payload == {"brightness": 75}
        finally:
            await ws_manager.remove_session("test-session-2")

    @pytest.mark.asyncio
    async def test_dispatch_increase_brightness(self, command_dispatcher, registered_device, device_service):
        """INCREASE_BRIGHTNESS should add 20 to current brightness."""
        from app.infra.websocket_manager import ws_manager, Session, SessionState

        # Set current brightness to 60
        await device_service.update_state(registered_device, {"brightness": 60})

        mock_ws = AsyncMock()
        test_session = Session(
            session_id="test-session-3",
            device_id=registered_device,
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await ws_manager.register_session(test_session)

        try:
            intent = ParsedIntent(intent=IntentType.INCREASE_BRIGHTNESS)
            command = await command_dispatcher.dispatch(registered_device, intent)

            assert command.type == "SET_BRIGHTNESS"
            assert command.payload == {"brightness": 80}
        finally:
            await ws_manager.remove_session("test-session-3")

    @pytest.mark.asyncio
    async def test_dispatch_increase_brightness_clamps_to_100(self, command_dispatcher, registered_device, device_service):
        """INCREASE_BRIGHTNESS from 90 should clamp to 100."""
        from app.infra.websocket_manager import ws_manager, Session, SessionState

        await device_service.update_state(registered_device, {"brightness": 90})

        mock_ws = AsyncMock()
        test_session = Session(
            session_id="test-session-4",
            device_id=registered_device,
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await ws_manager.register_session(test_session)

        try:
            intent = ParsedIntent(intent=IntentType.INCREASE_BRIGHTNESS)
            command = await command_dispatcher.dispatch(registered_device, intent)

            assert command.payload == {"brightness": 100}
        finally:
            await ws_manager.remove_session("test-session-4")

    @pytest.mark.asyncio
    async def test_dispatch_decrease_brightness_clamps_to_0(self, command_dispatcher, registered_device, device_service):
        """DECREASE_BRIGHTNESS from 10 should clamp to 0."""
        from app.infra.websocket_manager import ws_manager, Session, SessionState

        await device_service.update_state(registered_device, {"brightness": 10})

        mock_ws = AsyncMock()
        test_session = Session(
            session_id="test-session-5",
            device_id=registered_device,
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await ws_manager.register_session(test_session)

        try:
            intent = ParsedIntent(intent=IntentType.DECREASE_BRIGHTNESS)
            command = await command_dispatcher.dispatch(registered_device, intent)

            assert command.payload == {"brightness": 0}
        finally:
            await ws_manager.remove_session("test-session-5")

    @pytest.mark.asyncio
    async def test_dispatch_play_music(self, command_dispatcher, registered_device):
        """Dispatch PLAY_MUSIC with music type."""
        from app.infra.websocket_manager import ws_manager, Session, SessionState

        mock_ws = AsyncMock()
        test_session = Session(
            session_id="test-session-6",
            device_id=registered_device,
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await ws_manager.register_session(test_session)

        try:
            intent = ParsedIntent(
                intent=IntentType.PLAY_MUSIC,
                params={"music_type": "RAIN", "duration_seconds": 900},
            )
            command = await command_dispatcher.dispatch(registered_device, intent)

            assert command.type == "PLAY_MUSIC"
            assert command.payload["musicType"] == "RAIN"
            assert command.payload["durationSeconds"] == 900
        finally:
            await ws_manager.remove_session("test-session-6")


class TestCommandAck:
    @pytest.mark.asyncio
    async def test_handle_success_ack(self, command_dispatcher, registered_device):
        """Successful ACK should update command status and device state."""
        from app.infra.websocket_manager import ws_manager, Session, SessionState

        mock_ws = AsyncMock()
        test_session = Session(
            session_id="test-session-7",
            device_id=registered_device,
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await ws_manager.register_session(test_session)

        try:
            # Dispatch a command first
            intent = ParsedIntent(intent=IntentType.TURN_ON_LIGHT)
            command = await command_dispatcher.dispatch(registered_device, intent)

            # Simulate ACK
            ack = CommandAck(
                messageType="COMMAND_ACK",
                commandId=command.commandId,
                deviceId=registered_device,
                status="SUCCESS",
                state={"lightPower": True, "brightness": 50},
                timestamp="2026-05-27T10:00:02Z",
            )
            await command_dispatcher.handle_ack(ack)

            # Verify device state updated
            from app.services.device_service import DeviceService
            device_service = command_dispatcher.device_service
            state = await device_service.get_state(registered_device)
            assert state.light_power is True
        finally:
            await ws_manager.remove_session("test-session-7")

    @pytest.mark.asyncio
    async def test_handle_failed_ack(self, command_dispatcher, registered_device):
        """Failed ACK should update command status."""
        from app.infra.websocket_manager import ws_manager, Session, SessionState

        mock_ws = AsyncMock()
        test_session = Session(
            session_id="test-session-8",
            device_id=registered_device,
            websocket=mock_ws,
            state=SessionState.IDLE,
        )
        await ws_manager.register_session(test_session)

        try:
            intent = ParsedIntent(intent=IntentType.TURN_ON_LIGHT)
            command = await command_dispatcher.dispatch(registered_device, intent)

            ack = CommandAck(
                messageType="COMMAND_ACK",
                commandId=command.commandId,
                deviceId=registered_device,
                status="FAILED",
                error="hardware_error",
                timestamp="2026-05-27T10:00:02Z",
            )
            await command_dispatcher.handle_ack(ack)

            # Verify command status in DB
            cmd_record = await command_dispatcher.repo.get_by_command_id(command.commandId)
            assert cmd_record.status == "FAILED"
            assert cmd_record.failure_reason == "hardware_error"
        finally:
            await ws_manager.remove_session("test-session-8")
