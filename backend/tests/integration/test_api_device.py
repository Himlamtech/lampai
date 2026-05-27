"""Integration tests for device service and API logic."""
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from app.infra.database import Base
from app.infra.models import DeviceModel  # noqa: register models
from app.core.config import settings
from app.services.device_service import DeviceService, validate_device_id
from app.core.errors import ValidationError


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
def device_service(session):
    return DeviceService(session)


class TestDeviceRegistration:
    @pytest.mark.asyncio
    async def test_register_device(self, device_service):
        state = await device_service.register("AA:BB:CC:DD:EE:FF")
        assert state.device_id == "AA:BB:CC:DD:EE:FF"
        assert state.brightness == 50
        assert state.status.value == "OFFLINE"
        assert state.light_power is False

    @pytest.mark.asyncio
    async def test_register_device_idempotent(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:01")
        state = await device_service.register("AA:BB:CC:DD:EE:01")
        assert state.device_id == "AA:BB:CC:DD:EE:01"

    @pytest.mark.asyncio
    async def test_register_invalid_device_id(self, device_service):
        with pytest.raises(ValidationError):
            await device_service.register("invalid-id")

    @pytest.mark.asyncio
    async def test_register_test_device_id(self, device_service):
        state = await device_service.register("TE:ST:00:00:00:01")
        assert state.device_id == "TE:ST:00:00:00:01"


class TestDeviceHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_success(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:02")
        success = await device_service.heartbeat("AA:BB:CC:DD:EE:02")
        assert success is True
        # Verify state is now ONLINE
        state = await device_service.get_state("AA:BB:CC:DD:EE:02")
        assert state.status.value == "ONLINE"
        assert state.last_seen_at is not None

    @pytest.mark.asyncio
    async def test_heartbeat_unknown_device(self, device_service):
        success = await device_service.heartbeat("AA:BB:CC:DD:EE:99")
        assert success is False


class TestDeviceState:
    @pytest.mark.asyncio
    async def test_get_state(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:03")
        state = await device_service.get_state("AA:BB:CC:DD:EE:03")
        assert state is not None
        assert state.device_id == "AA:BB:CC:DD:EE:03"
        assert state.brightness == 50

    @pytest.mark.asyncio
    async def test_get_state_not_found(self, device_service):
        state = await device_service.get_state("AA:BB:CC:DD:EE:99")
        assert state is None

    @pytest.mark.asyncio
    async def test_update_state_brightness(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:04")
        state = await device_service.update_state("AA:BB:CC:DD:EE:04", {"brightness": 75})
        assert state is not None
        assert state.brightness == 75

    @pytest.mark.asyncio
    async def test_update_state_invalid_brightness_over_100(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:05")
        with pytest.raises(ValidationError):
            await device_service.update_state("AA:BB:CC:DD:EE:05", {"brightness": 150})

    @pytest.mark.asyncio
    async def test_update_state_invalid_brightness_negative(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:07")
        with pytest.raises(ValidationError):
            await device_service.update_state("AA:BB:CC:DD:EE:07", {"brightness": -1})

    @pytest.mark.asyncio
    async def test_update_state_brightness_boundary_0(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:08")
        state = await device_service.update_state("AA:BB:CC:DD:EE:08", {"brightness": 0})
        assert state.brightness == 0

    @pytest.mark.asyncio
    async def test_update_state_brightness_boundary_100(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:09")
        state = await device_service.update_state("AA:BB:CC:DD:EE:09", {"brightness": 100})
        assert state.brightness == 100

    @pytest.mark.asyncio
    async def test_update_state_multiple_fields(self, device_service):
        await device_service.register("AA:BB:CC:DD:EE:06")
        state = await device_service.update_state(
            "AA:BB:CC:DD:EE:06",
            {"brightness": 30, "light_power": True, "mode": "SLEEP"},
        )
        assert state.brightness == 30
        assert state.light_power is True
        assert state.mode == "SLEEP"

    @pytest.mark.asyncio
    async def test_update_state_not_found(self, device_service):
        state = await device_service.update_state("AA:BB:CC:DD:EE:99", {"brightness": 50})
        assert state is None


class TestHeartbeatTimeout:
    @pytest.mark.asyncio
    async def test_mark_offline_stale_devices(self, device_service, session):
        """Devices that haven't sent heartbeat should be marked offline."""
        await device_service.register("AA:BB:CC:DD:EE:0A")
        # Manually set last_seen_at to 2 minutes ago
        from datetime import datetime, timezone, timedelta
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        await session.execute(
            text("UPDATE devices SET status='ONLINE', last_seen_at=:ts WHERE device_id=:did"),
            {"ts": old_time, "did": "AA:BB:CC:DD:EE:0A"},
        )
        await session.commit()

        stale = await device_service.mark_offline_stale_devices()
        assert "AA:BB:CC:DD:EE:0A" in stale

        state = await device_service.get_state("AA:BB:CC:DD:EE:0A")
        assert state.status.value == "OFFLINE"
