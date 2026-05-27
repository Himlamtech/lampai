from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import DeviceModel
from app.domain.device_state import DeviceState, DeviceStatus


class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, device_id: str, client_id: str | None = None) -> DeviceState:
        device = DeviceModel(
            device_id=device_id,
            client_id=client_id,
            status=DeviceStatus.OFFLINE.value,
        )
        self.session.add(device)
        await self.session.commit()
        await self.session.refresh(device)
        return self._to_domain(device)

    async def get_by_id(self, device_id: str) -> DeviceState | None:
        result = await self.session.execute(
            select(DeviceModel).where(DeviceModel.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if device is None:
            return None
        return self._to_domain(device)

    async def update_heartbeat(self, device_id: str) -> bool:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(DeviceModel)
            .where(DeviceModel.device_id == device_id)
            .values(last_seen_at=now, status=DeviceStatus.ONLINE.value, updated_at=now)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def update_state(self, device_id: str, updates: dict) -> DeviceState | None:
        updates["updated_at"] = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(DeviceModel)
            .where(DeviceModel.device_id == device_id)
            .values(**updates)
            .returning(DeviceModel)
        )
        await self.session.commit()
        device = result.scalar_one_or_none()
        if device is None:
            return None
        return self._to_domain(device)

    async def mark_offline(self, device_id: str) -> None:
        await self.session.execute(
            update(DeviceModel)
            .where(DeviceModel.device_id == device_id)
            .values(status=DeviceStatus.OFFLINE.value, updated_at=datetime.now(timezone.utc))
        )
        await self.session.commit()

    async def get_stale_online_devices(self, threshold: datetime) -> list[str]:
        result = await self.session.execute(
            select(DeviceModel.device_id).where(
                DeviceModel.status == DeviceStatus.ONLINE.value,
                DeviceModel.last_seen_at < threshold,
            )
        )
        return list(result.scalars().all())

    async def get_all(self) -> list[DeviceState]:
        result = await self.session.execute(select(DeviceModel))
        return [self._to_domain(d) for d in result.scalars().all()]

    def _to_domain(self, model: DeviceModel) -> DeviceState:
        return DeviceState(
            device_id=model.device_id,
            status=DeviceStatus(model.status),
            light_power=model.light_power,
            brightness=model.brightness,
            color=model.color,
            mode=model.mode,
            volume=model.volume,
            is_playing_music=model.is_playing_music,
            last_seen_at=model.last_seen_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
