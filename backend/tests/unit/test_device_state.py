import pytest
from pydantic import ValidationError as PydanticValidationError
from app.domain.device_state import DeviceState, DeviceStatus
from app.services.device_service import validate_device_id
from app.core.errors import ValidationError


class TestDeviceState:
    def test_default_values(self):
        state = DeviceState(device_id="AA:BB:CC:DD:EE:FF")
        assert state.status == DeviceStatus.OFFLINE
        assert state.light_power is False
        assert state.brightness == 50
        assert state.color == "#FFD27D"
        assert state.mode == "NORMAL"
        assert state.volume == 60
        assert state.is_playing_music is False

    def test_brightness_valid_range(self):
        state = DeviceState(device_id="AA:BB:CC:DD:EE:FF", brightness=0)
        assert state.brightness == 0
        state = DeviceState(device_id="AA:BB:CC:DD:EE:FF", brightness=100)
        assert state.brightness == 100

    def test_brightness_invalid_below_zero(self):
        with pytest.raises(PydanticValidationError):
            DeviceState(device_id="AA:BB:CC:DD:EE:FF", brightness=-1)

    def test_brightness_invalid_above_100(self):
        with pytest.raises(PydanticValidationError):
            DeviceState(device_id="AA:BB:CC:DD:EE:FF", brightness=101)

    def test_volume_valid_range(self):
        state = DeviceState(device_id="AA:BB:CC:DD:EE:FF", volume=0)
        assert state.volume == 0
        state = DeviceState(device_id="AA:BB:CC:DD:EE:FF", volume=100)
        assert state.volume == 100

    def test_volume_invalid(self):
        with pytest.raises(PydanticValidationError):
            DeviceState(device_id="AA:BB:CC:DD:EE:FF", volume=101)


class TestDeviceIdValidation:
    def test_valid_mac_address(self):
        valid_ids = [
            "AA:BB:CC:DD:EE:FF",
            "aa:bb:cc:dd:ee:ff",
            "00:11:22:33:44:55",
            "TE:ST:00:00:00:01",
        ]
        for device_id in valid_ids:
            validate_device_id(device_id)  # Should not raise

    def test_invalid_mac_address(self):
        invalid_ids = [
            "not-a-mac",
            "AA:BB:CC:DD:EE",  # too short
            "AA:BB:CC:DD:EE:FF:GG",  # too long
            "AABBCCDDEEFF",  # no colons
            "AA-BB-CC-DD-EE-FF",  # wrong separator
            "",
            "GG:HH:II:JJ:KK:LL",  # invalid hex
        ]
        for device_id in invalid_ids:
            with pytest.raises(ValidationError):
                validate_device_id(device_id)
