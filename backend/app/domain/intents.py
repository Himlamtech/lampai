from enum import Enum
from pydantic import BaseModel
from typing import Literal


class IntentType(str, Enum):
    TURN_ON_LIGHT = "TURN_ON_LIGHT"
    TURN_OFF_LIGHT = "TURN_OFF_LIGHT"
    INCREASE_BRIGHTNESS = "INCREASE_BRIGHTNESS"
    DECREASE_BRIGHTNESS = "DECREASE_BRIGHTNESS"
    SET_BRIGHTNESS = "SET_BRIGHTNESS"
    CHANGE_LIGHT_MODE = "CHANGE_LIGHT_MODE"
    PLAY_MUSIC = "PLAY_MUSIC"
    STOP_MUSIC = "STOP_MUSIC"
    ASK_WEATHER = "ASK_WEATHER"
    ASK_TIME = "ASK_TIME"
    ASK_GENERAL_INFO = "ASK_GENERAL_INFO"
    CHAT = "CHAT"
    UNKNOWN = "UNKNOWN"


HARDWARE_INTENTS = {
    IntentType.TURN_ON_LIGHT,
    IntentType.TURN_OFF_LIGHT,
    IntentType.INCREASE_BRIGHTNESS,
    IntentType.DECREASE_BRIGHTNESS,
    IntentType.SET_BRIGHTNESS,
    IntentType.CHANGE_LIGHT_MODE,
    IntentType.PLAY_MUSIC,
    IntentType.STOP_MUSIC,
}

INFO_INTENTS = {
    IntentType.ASK_WEATHER,
    IntentType.ASK_TIME,
    IntentType.ASK_GENERAL_INFO,
}


class ParsedIntent(BaseModel):
    intent: IntentType
    confidence: float = 1.0
    params: dict = {}
    source: Literal["deterministic", "llm", "admin"] = "deterministic"
    error: str | None = None
