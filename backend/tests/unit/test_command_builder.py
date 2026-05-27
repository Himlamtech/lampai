"""Tests for command building and brightness clamping logic."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.domain.intents import IntentType, ParsedIntent
from app.domain.commands import CommandType
from app.services.command_service import _intent_to_command_type, _generate_command_id


class TestIntentToCommandType:
    def test_turn_on_light(self):
        assert _intent_to_command_type(IntentType.TURN_ON_LIGHT) == "TURN_ON_LIGHT"

    def test_turn_off_light(self):
        assert _intent_to_command_type(IntentType.TURN_OFF_LIGHT) == "TURN_OFF_LIGHT"

    def test_set_brightness(self):
        assert _intent_to_command_type(IntentType.SET_BRIGHTNESS) == "SET_BRIGHTNESS"

    def test_increase_brightness_maps_to_set(self):
        assert _intent_to_command_type(IntentType.INCREASE_BRIGHTNESS) == "SET_BRIGHTNESS"

    def test_decrease_brightness_maps_to_set(self):
        assert _intent_to_command_type(IntentType.DECREASE_BRIGHTNESS) == "SET_BRIGHTNESS"

    def test_change_light_mode(self):
        assert _intent_to_command_type(IntentType.CHANGE_LIGHT_MODE) == "CHANGE_LIGHT_MODE"

    def test_play_music(self):
        assert _intent_to_command_type(IntentType.PLAY_MUSIC) == "PLAY_MUSIC"

    def test_stop_music(self):
        assert _intent_to_command_type(IntentType.STOP_MUSIC) == "STOP_MUSIC"


class TestCommandIdGeneration:
    def test_generates_unique_ids(self):
        ids = {_generate_command_id() for _ in range(100)}
        assert len(ids) == 100

    def test_starts_with_cmd_prefix(self):
        cmd_id = _generate_command_id()
        assert cmd_id.startswith("cmd_")

    def test_has_reasonable_length(self):
        cmd_id = _generate_command_id()
        assert 10 < len(cmd_id) < 30


class TestBrightnessClamping:
    """Test brightness increase/decrease clamping logic."""

    def test_increase_from_50(self):
        current = 50
        new_brightness = min(current + 20, 100)
        assert new_brightness == 70

    def test_increase_from_90_clamps_to_100(self):
        current = 90
        new_brightness = min(current + 20, 100)
        assert new_brightness == 100

    def test_increase_from_100_stays_100(self):
        current = 100
        new_brightness = min(current + 20, 100)
        assert new_brightness == 100

    def test_decrease_from_50(self):
        current = 50
        new_brightness = max(current - 20, 0)
        assert new_brightness == 30

    def test_decrease_from_10_clamps_to_0(self):
        current = 10
        new_brightness = max(current - 20, 0)
        assert new_brightness == 0

    def test_decrease_from_0_stays_0(self):
        current = 0
        new_brightness = max(current - 20, 0)
        assert new_brightness == 0

    def test_increase_from_0(self):
        current = 0
        new_brightness = min(current + 20, 100)
        assert new_brightness == 20

    def test_decrease_from_100(self):
        current = 100
        new_brightness = max(current - 20, 0)
        assert new_brightness == 80
