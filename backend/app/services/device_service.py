import re
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.device_repository import DeviceRepository
from app.domain.device_state import DeviceState, DeviceStatus
from app.core.errors import ValidationError
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("device_service")

DEVICE_ID_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
# Test device IDs are allowed (TE:ST:xx:xx:xx:xx format)
TEST_DEVICE_ID_PATTERN = re.compile(r"^TE:ST(:[0-9A-Fa-f]{2}){4}$")


def validate_device_id(device_id: str) -> None:
    if not DEVICE_ID_PATTERN.match(device_id) and not TEST_DEVICE_ID_PATTERN.match(device_id):
        raise ValidationError(
            message=f"Invalid device_id format: {device_id}. Expected MAC address XX:XX:XX:XX:XX:XX",
            details={"device_id": device_id},
        )


class DeviceService:
    def __init__(self, session: AsyncSession):
        self.repo = DeviceRepository(session)

    async def register(self, device_id: str, client_id: str | None = None) -> DeviceState:
        validate_device_id(device_id)
        existing = await self.repo.get_by_id(device_id)
        if existing:
            logger.info("device_already_registered", device_id=device_id)
            return existing
        state = await self.repo.create(device_id, client_id)
        logger.info("device_registered", device_id=device_id)
        return state

    async def heartbeat(self, device_id: str) -> bool:
        validate_device_id(device_id)
        success = await self.repo.update_heartbeat(device_id)
        if success:
            logger.debug("device_heartbeat", device_id=device_id)
        else:
            logger.warning("device_heartbeat_unknown_device", device_id=device_id)
        return success

    async def get_state(self, device_id: str) -> DeviceState | None:
        validate_device_id(device_id)
        return await self.repo.get_by_id(device_id)

    async def update_state(self, device_id: str, updates: dict) -> DeviceState | None:
        validate_device_id(device_id)
        if "brightness" in updates:
            b = updates["brightness"]
            if not isinstance(b, int) or b < 0 or b > 100:
                raise ValidationError(
                    message=f"Brightness must be integer 0-100, got {b}",
                    details={"brightness": b},
                )
        if "volume" in updates:
            v = updates["volume"]
            if not isinstance(v, int) or v < 0 or v > 100:
                raise ValidationError(
                    message=f"Volume must be integer 0-100, got {v}",
                    details={"volume": v},
                )
        state = await self.repo.update_state(device_id, updates)
        if state:
            logger.info("device_state_updated", device_id=device_id, updates=updates)
        return state

    async def mark_offline_stale_devices(self) -> list[str]:
        threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.heartbeat_timeout_seconds)
        stale_ids = await self.repo.get_stale_online_devices(threshold)
        for device_id in stale_ids:
            await self.repo.mark_offline(device_id)
            logger.info("device_marked_offline", device_id=device_id, reason="heartbeat_timeout")
        return stale_ids

    async def get_all_devices(self) -> list[DeviceState]:
        return await self.repo.get_all()
