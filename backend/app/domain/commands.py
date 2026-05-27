from enum import Enum
from pydantic import BaseModel
from typing import Literal


class CommandType(str, Enum):
    TURN_ON_LIGHT = "TURN_ON_LIGHT"
    TURN_OFF_LIGHT = "TURN_OFF_LIGHT"
    SET_BRIGHTNESS = "SET_BRIGHTNESS"
    CHANGE_LIGHT_MODE = "CHANGE_LIGHT_MODE"
    PLAY_MUSIC = "PLAY_MUSIC"
    STOP_MUSIC = "STOP_MUSIC"
    PLAY_TTS_RESPONSE = "PLAY_TTS_RESPONSE"
    APPLY_LIGHT_EFFECT = "APPLY_LIGHT_EFFECT"


class CommandStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class DeviceCommand(BaseModel):
    messageType: Literal["COMMAND"] = "COMMAND"
    commandId: str
    deviceId: str
    type: str
    payload: dict = {}
    timestamp: str  # ISO 8601


class CommandAck(BaseModel):
    messageType: Literal["COMMAND_ACK"]
    commandId: str
    deviceId: str
    status: Literal["SUCCESS", "FAILED"]
    state: dict | None = None
    error: str | None = None
    timestamp: str
