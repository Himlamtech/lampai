from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class DeviceStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class DeviceState(BaseModel):
    device_id: str
    status: DeviceStatus = DeviceStatus.OFFLINE
    light_power: bool = False
    brightness: int = Field(default=50, ge=0, le=100)
    color: str = "#FFD27D"
    mode: str = "NORMAL"
    volume: int = Field(default=60, ge=0, le=100)
    is_playing_music: bool = False
    last_seen_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
