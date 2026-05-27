"""Speech-to-Text service abstraction and OpenAI Whisper implementation."""
import io
import wave
from abc import ABC, abstractmethod

from app.core.config import settings
from app.core.logging import get_logger
from app.core.errors import ProviderError

logger = get_logger("stt_service")


class STTService(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, sample_rate: int = 16000, language: str = "vi") -> str:
        """Transcribe audio bytes to text."""
        ...


class OpenAISTTService(STTService):
    """OpenAI Whisper-based STT service."""

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.model = settings.stt_model

    async def transcribe(self, audio: bytes, sample_rate: int = 16000, language: str = "vi") -> str:
        """Transcribe audio bytes (PCM or Opus) to text using OpenAI Whisper."""
        if not audio:
            raise ProviderError("stt", "Empty audio buffer")

        try:
            # Convert raw PCM to WAV format for the API
            wav_buffer = self._pcm_to_wav(audio, sample_rate)

            # Call OpenAI transcription API
            lang_code = language if language != "auto" else None

            transcript = await self.client.audio.transcriptions.create(
                model=self.model,
                file=("audio.wav", wav_buffer, "audio/wav"),
                language=lang_code,
            )

            text = transcript.text.strip()
            logger.info("stt_transcription_complete", text_length=len(text), language=language)
            return text

        except Exception as e:
            logger.error("stt_transcription_failed", error=str(e))
            raise ProviderError("stt", f"Transcription failed: {e}")

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int) -> bytes:
        """Convert raw PCM bytes to WAV format."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        buffer.seek(0)
        return buffer.read()


class MockSTTService(STTService):
    """Mock STT service for testing."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []
        self.default_response = "xin chào"

    async def transcribe(self, audio: bytes, sample_rate: int = 16000, language: str = "vi") -> str:
        self.calls.append({"audio_size": len(audio), "sample_rate": sample_rate, "language": language})
        # Return based on audio size hash for deterministic testing
        key = str(len(audio))
        return self.responses.get(key, self.default_response)
