from pydantic import BaseModel, Field
from typing import Literal


class AudioParams(BaseModel):
    format: Literal["opus"] = "opus"
    sample_rate: int = 16000
    channels: Literal[1] = 1
    frame_duration: int = 60


class HelloMessage(BaseModel):
    type: Literal["hello"]
    version: int
    transport: Literal["websocket"]
    audio_params: AudioParams
    features: dict[str, bool] = {}


class ServerHelloResponse(BaseModel):
    type: Literal["hello"] = "hello"
    transport: Literal["websocket"] = "websocket"
    session_id: str
    audio_params: AudioParams = AudioParams(sample_rate=24000)


class ConnectionHeaders(BaseModel):
    authorization: str
    protocol_version: int
    device_id: str
    client_id: str


class DeviceRegisterRequest(BaseModel):
    device_id: str


class DeviceStateResponse(BaseModel):
    device_id: str = Field(alias="deviceId")
    status: str
    light_power: bool = Field(alias="lightPower")
    brightness: int
    color: str
    mode: str
    volume: int
    is_playing_music: bool = Field(alias="isPlayingMusic")
    last_seen_at: str | None = Field(alias="lastSeenAt", default=None)

    model_config = {"populate_by_name": True}


class DeviceStateUpdateRequest(BaseModel):
    light_power: bool | None = Field(None, alias="lightPower")
    brightness: int | None = Field(None, ge=0, le=100)
    color: str | None = None
    mode: str | None = None
    volume: int | None = Field(None, ge=0, le=100)
    is_playing_music: bool | None = Field(None, alias="isPlayingMusic")

    model_config = {"populate_by_name": True}
