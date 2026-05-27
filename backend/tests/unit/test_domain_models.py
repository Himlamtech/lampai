import pytest
from app.domain.intents import IntentType, ParsedIntent, HARDWARE_INTENTS, INFO_INTENTS
from app.domain.commands import DeviceCommand, CommandAck, CommandStatus, CommandType
from app.schemas.device import HelloMessage, AudioParams, ServerHelloResponse, ConnectionHeaders


class TestIntentType:
    def test_all_intents_defined(self):
        expected = {
            "TURN_ON_LIGHT", "TURN_OFF_LIGHT", "INCREASE_BRIGHTNESS",
            "DECREASE_BRIGHTNESS", "SET_BRIGHTNESS", "CHANGE_LIGHT_MODE",
            "PLAY_MUSIC", "STOP_MUSIC", "ASK_WEATHER", "ASK_TIME",
            "ASK_GENERAL_INFO", "CHAT", "UNKNOWN",
        }
        actual = {e.value for e in IntentType}
        assert actual == expected

    def test_hardware_intents_set(self):
        assert IntentType.TURN_ON_LIGHT in HARDWARE_INTENTS
        assert IntentType.PLAY_MUSIC in HARDWARE_INTENTS
        assert IntentType.CHAT not in HARDWARE_INTENTS
        assert IntentType.ASK_WEATHER not in HARDWARE_INTENTS

    def test_info_intents_set(self):
        assert IntentType.ASK_WEATHER in INFO_INTENTS
        assert IntentType.ASK_TIME in INFO_INTENTS
        assert IntentType.CHAT not in INFO_INTENTS


class TestParsedIntent:
    def test_default_values(self):
        intent = ParsedIntent(intent=IntentType.TURN_ON_LIGHT)
        assert intent.confidence == 1.0
        assert intent.params == {}
        assert intent.source == "deterministic"
        assert intent.error is None

    def test_with_params(self):
        intent = ParsedIntent(
            intent=IntentType.SET_BRIGHTNESS,
            params={"brightness": 50},
            source="deterministic",
        )
        assert intent.params["brightness"] == 50


class TestDeviceCommand:
    def test_command_structure(self):
        cmd = DeviceCommand(
            commandId="cmd_001",
            deviceId="AA:BB:CC:DD:EE:FF",
            type="TURN_ON_LIGHT",
            payload={},
            timestamp="2026-05-27T10:00:00Z",
        )
        assert cmd.messageType == "COMMAND"
        assert cmd.commandId == "cmd_001"
        assert cmd.type == "TURN_ON_LIGHT"


class TestCommandAck:
    def test_success_ack(self):
        ack = CommandAck(
            messageType="COMMAND_ACK",
            commandId="cmd_001",
            deviceId="AA:BB:CC:DD:EE:FF",
            status="SUCCESS",
            state={"lightPower": True, "brightness": 50},
            timestamp="2026-05-27T10:00:02Z",
        )
        assert ack.status == "SUCCESS"
        assert ack.state["lightPower"] is True

    def test_failed_ack(self):
        ack = CommandAck(
            messageType="COMMAND_ACK",
            commandId="cmd_001",
            deviceId="AA:BB:CC:DD:EE:FF",
            status="FAILED",
            error="hardware_error",
            timestamp="2026-05-27T10:00:02Z",
        )
        assert ack.status == "FAILED"
        assert ack.error == "hardware_error"


class TestHelloMessage:
    def test_valid_hello(self):
        msg = HelloMessage(
            type="hello",
            version=1,
            transport="websocket",
            audio_params=AudioParams(format="opus", sample_rate=16000, channels=1, frame_duration=60),
        )
        assert msg.type == "hello"
        assert msg.audio_params.sample_rate == 16000

    def test_server_hello_response(self):
        resp = ServerHelloResponse(session_id="test-session-123")
        assert resp.type == "hello"
        assert resp.transport == "websocket"
        assert resp.session_id == "test-session-123"
        assert resp.audio_params.sample_rate == 24000


class TestConnectionHeaders:
    def test_valid_headers(self):
        headers = ConnectionHeaders(
            authorization="Bearer test-token",
            protocol_version=1,
            device_id="AA:BB:CC:DD:EE:FF",
            client_id="550e8400-e29b-41d4-a716-446655440000",
        )
        assert headers.authorization == "Bearer test-token"
        assert headers.protocol_version == 1
