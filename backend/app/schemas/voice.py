from pydantic import BaseModel
from typing import Literal


class ListenMessage(BaseModel):
    session_id: str
    type: Literal["listen"]
    state: Literal["start", "stop", "detect"]
    mode: Literal["auto", "manual", "realtime"] | None = None
    text: str | None = None


class STTResult(BaseModel):
    session_id: str
    type: Literal["stt"] = "stt"
    text: str


class TTSControl(BaseModel):
    session_id: str
    type: Literal["tts"] = "tts"
    state: Literal["start", "stop", "sentence_start"]
    text: str | None = None


class AbortMessage(BaseModel):
    session_id: str
    type: Literal["abort"]
    reason: str | None = None
