"""Text-to-Speech service abstraction and OpenAI TTS-1 implementation."""
import io
from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.core.config import settings
from app.core.logging import get_logger
from app.core.errors import ProviderError

logger = get_logger("tts_service")


class TTSService(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str = "nova", speed: float = 1.0) -> bytes:
        """Synthesize text to audio bytes (PCM or encoded format)."""
        ...

    @abstractmethod
    async def synthesize_streaming(self, text: str, voice: str = "nova", speed: float = 1.0) -> AsyncIterator[bytes]:
        """Synthesize text to audio, yielding chunks for streaming."""
        ...


class OpenAITTSService(TTSService):
    """OpenAI TTS-1 based text-to-speech service."""

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.model = settings.tts_model

    async def synthesize(self, text: str, voice: str = "nova", speed: float = 1.0) -> bytes:
        """Synthesize text to audio bytes (opus format)."""
        if not text.strip():
            raise ProviderError("tts", "Empty text input")

        try:
            response = await self.client.audio.speech.create(
                model=self.model,
                voice=voice,
                input=text,
                speed=speed,
                response_format="opus",
            )

            audio_bytes = response.content
            logger.info(
                "tts_synthesis_complete",
                text_length=len(text),
                audio_size=len(audio_bytes),
                voice=voice,
                speed=speed,
            )
            return audio_bytes

        except Exception as e:
            logger.error("tts_synthesis_failed", error=str(e), text_length=len(text))
            raise ProviderError("tts", f"TTS synthesis failed: {e}")

    async def synthesize_streaming(self, text: str, voice: str = "nova", speed: float = 1.0) -> AsyncIterator[bytes]:
        """Synthesize text and yield audio chunks for streaming."""
        if not text.strip():
            raise ProviderError("tts", "Empty text input")

        try:
            response = await self.client.audio.speech.create(
                model=self.model,
                voice=voice,
                input=text,
                speed=speed,
                response_format="opus",
            )

            # Yield the full response as chunks (OpenAI returns complete audio)
            # Split into ~960 byte chunks (roughly 60ms of Opus at typical bitrate)
            content = response.content
            chunk_size = 960
            for i in range(0, len(content), chunk_size):
                yield content[i:i + chunk_size]

            logger.info(
                "tts_streaming_complete",
                text_length=len(text),
                total_size=len(content),
                voice=voice,
            )

        except Exception as e:
            logger.error("tts_streaming_failed", error=str(e))
            raise ProviderError("tts", f"TTS streaming failed: {e}")


class MockTTSService(TTSService):
    """Mock TTS service for testing."""

    def __init__(self):
        self.calls: list[dict] = []
        # Generate silent Opus-like bytes for testing
        self._silent_frame = b"\x00" * 960

    async def synthesize(self, text: str, voice: str = "nova", speed: float = 1.0) -> bytes:
        self.calls.append({"text": text, "voice": voice, "speed": speed})
        # Return fake audio data (10 frames of silence)
        return self._silent_frame * 10

    async def synthesize_streaming(self, text: str, voice: str = "nova", speed: float = 1.0) -> AsyncIterator[bytes]:
        self.calls.append({"text": text, "voice": voice, "speed": speed, "streaming": True})
        # Yield 10 silent frames
        for _ in range(10):
            yield self._silent_frame
