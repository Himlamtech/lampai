"""Voice pipeline orchestration — the core processing chain."""
import time
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.core.errors import ProviderError, DeviceOfflineError
from app.domain.intents import IntentType, ParsedIntent, HARDWARE_INTENTS, INFO_INTENTS
from app.services.intent_service import IntentParser
from app.services.stt_service import STTService
from app.services.tts_service import TTSService
from app.services.llm_service import LLMService, ConversationTurn

logger = get_logger("voice_pipeline")


@dataclass
class PipelineResult:
    user_text: str = ""
    intent: ParsedIntent | None = None
    ai_response: str = ""
    tts_audio: bytes = b""
    command_sent: bool = False
    command_id: str | None = None
    error: str | None = None
    stage_latencies: dict = field(default_factory=dict)

    @property
    def total_latency_ms(self) -> int:
        return sum(self.stage_latencies.values())


# Confirmation messages for hardware commands
CONFIRMATIONS_VI = {
    IntentType.TURN_ON_LIGHT: "Đã bật đèn.",
    IntentType.TURN_OFF_LIGHT: "Đã tắt đèn.",
    IntentType.SET_BRIGHTNESS: "Đã chỉnh độ sáng.",
    IntentType.INCREASE_BRIGHTNESS: "Đã tăng sáng.",
    IntentType.DECREASE_BRIGHTNESS: "Đã giảm sáng.",
    IntentType.CHANGE_LIGHT_MODE: "Đã đổi chế độ.",
    IntentType.PLAY_MUSIC: "Đang phát nhạc.",
    IntentType.STOP_MUSIC: "Đã dừng nhạc.",
}

CONFIRMATIONS_EN = {
    IntentType.TURN_ON_LIGHT: "Light is on.",
    IntentType.TURN_OFF_LIGHT: "Light is off.",
    IntentType.SET_BRIGHTNESS: "Brightness adjusted.",
    IntentType.INCREASE_BRIGHTNESS: "Brightness increased.",
    IntentType.DECREASE_BRIGHTNESS: "Brightness decreased.",
    IntentType.CHANGE_LIGHT_MODE: "Mode changed.",
    IntentType.PLAY_MUSIC: "Playing music.",
    IntentType.STOP_MUSIC: "Music stopped.",
}

FALLBACK_VI = "Mình chưa nghe rõ, bạn nói lại được không?"
FALLBACK_EN = "I didn't catch that, could you repeat?"
FALLBACK_LLM_VI = "Xin lỗi, mình đang gặp trục trặc. Bạn thử lại sau nhé."
FALLBACK_LLM_EN = "Sorry, I'm having trouble right now. Please try again."
FALLBACK_INFO_VI = "Dịch vụ tạm thời không khả dụng."
FALLBACK_INFO_EN = "Service temporarily unavailable."


def _get_fallback(key: str) -> str:
    mapping = {
        "stt": FALLBACK_VI if settings.language == "vi" else FALLBACK_EN,
        "llm": FALLBACK_LLM_VI if settings.language == "vi" else FALLBACK_LLM_EN,
        "info": FALLBACK_INFO_VI if settings.language == "vi" else FALLBACK_INFO_EN,
    }
    return mapping.get(key, FALLBACK_VI if settings.language == "vi" else FALLBACK_EN)


def _get_confirmation(intent: IntentType) -> str:
    if settings.language == "vi":
        return CONFIRMATIONS_VI.get(intent, "Đã thực hiện.")
    return CONFIRMATIONS_EN.get(intent, "Done.")


class VoicePipeline:
    def __init__(
        self,
        stt_service: STTService,
        tts_service: TTSService,
        llm_service: LLMService,
        intent_parser: IntentParser | None = None,
    ):
        self.stt = stt_service
        self.tts = tts_service
        self.llm = llm_service
        self.intent_parser = intent_parser or IntentParser()

    async def process_audio(
        self,
        audio_buffer: bytes,
        device_id: str,
        session_id: str,
        context: list[ConversationTurn] | None = None,
        system_prompt: str = "",
        voice: str = "",
        speed: float = 0,
    ) -> PipelineResult:
        """Process audio through full pipeline: STT → Intent → Route → Response → TTS."""
        result = PipelineResult()
        voice = voice or settings.tts_voice
        speed = speed or settings.tts_speed

        # Stage 1: STT
        t0 = time.time()
        try:
            text = await self.stt.transcribe(audio_buffer, sample_rate=16000, language=settings.language)
            result.user_text = text
            result.stage_latencies["stt"] = int((time.time() - t0) * 1000)
        except ProviderError:
            result.stage_latencies["stt"] = int((time.time() - t0) * 1000)
            result.ai_response = _get_fallback("stt")
            result.error = "stt_failed"
            result.tts_audio = await self._safe_tts(result.ai_response, voice, speed)
            logger.warning("pipeline_stt_failed", device_id=device_id, session_id=session_id)
            return result

        if not text.strip():
            result.ai_response = _get_fallback("stt")
            result.error = "stt_empty"
            result.tts_audio = await self._safe_tts(result.ai_response, voice, speed)
            return result

        # Continue with text processing
        return await self._process_from_text(result, device_id, session_id, context, system_prompt, voice, speed)

    async def process_text(
        self,
        text: str,
        device_id: str,
        session_id: str,
        context: list[ConversationTurn] | None = None,
        system_prompt: str = "",
        voice: str = "",
        speed: float = 0,
    ) -> PipelineResult:
        """Process text input (skip STT): Intent → Route → Response → TTS."""
        result = PipelineResult(user_text=text)
        voice = voice or settings.tts_voice
        speed = speed or settings.tts_speed
        return await self._process_from_text(result, device_id, session_id, context, system_prompt, voice, speed)

    async def _process_from_text(
        self,
        result: PipelineResult,
        device_id: str,
        session_id: str,
        context: list[ConversationTurn] | None,
        system_prompt: str,
        voice: str,
        speed: float,
    ) -> PipelineResult:
        """Process from text through intent parsing, routing, and response generation."""
        # Stage 2: Intent parsing
        t0 = time.time()
        intent = await self.intent_parser.parse(result.user_text)
        result.intent = intent
        result.stage_latencies["intent"] = int((time.time() - t0) * 1000)

        # Stage 3: Route by intent type
        t0 = time.time()
        if intent.intent in HARDWARE_INTENTS:
            # Hardware commands bypass LLM
            confirmation = _get_confirmation(intent.intent)
            result.ai_response = confirmation
            result.command_sent = True
            result.stage_latencies["routing"] = int((time.time() - t0) * 1000)

        elif intent.intent in INFO_INTENTS:
            # Information requests
            try:
                response = await self._handle_info_intent(intent, result.user_text)
                result.ai_response = response
            except Exception as e:
                result.ai_response = _get_fallback("info")
                result.error = f"info_failed: {e}"
            result.stage_latencies["routing"] = int((time.time() - t0) * 1000)

        elif intent.intent == IntentType.CHAT:
            # Chat with LLM
            try:
                response = await self.llm.generate(
                    user_message=result.user_text,
                    system_prompt=system_prompt,
                    context=context,
                )
                result.ai_response = response
            except ProviderError:
                result.ai_response = _get_fallback("llm")
                result.error = "llm_failed"
            result.stage_latencies["llm"] = int((time.time() - t0) * 1000)

        else:
            # UNKNOWN intent
            result.ai_response = _get_fallback("stt")
            result.stage_latencies["routing"] = int((time.time() - t0) * 1000)

        # Stage 4: TTS
        t0 = time.time()
        if result.ai_response:
            result.tts_audio = await self._safe_tts(result.ai_response, voice, speed)
        result.stage_latencies["tts"] = int((time.time() - t0) * 1000)

        logger.info(
            "pipeline_complete",
            device_id=device_id,
            session_id=session_id,
            intent=intent.intent.value,
            user_text=result.user_text[:50],
            response_length=len(result.ai_response),
            total_latency_ms=result.total_latency_ms,
            stage_latencies=result.stage_latencies,
        )

        return result

    async def _handle_info_intent(self, intent: ParsedIntent, user_text: str) -> str:
        """Handle information intents (weather, time, general info)."""
        if intent.intent == IntentType.ASK_TIME:
            from datetime import datetime
            import zoneinfo
            tz = zoneinfo.ZoneInfo(settings.timezone)
            now = datetime.now(tz)
            if settings.language == "vi":
                return f"Bây giờ là {now.strftime('%H giờ %M phút')}."
            return f"It's {now.strftime('%I:%M %p')}."

        elif intent.intent == IntentType.ASK_WEATHER:
            # For MVP, use LLM to answer weather questions
            response = await self.llm.generate(
                user_message=user_text,
                system_prompt="Trả lời ngắn gọn về thời tiết. Nếu không có dữ liệu thực, hãy nói rằng bạn không có thông tin thời tiết real-time nhưng có thể gợi ý chung.",
            )
            return response

        elif intent.intent == IntentType.ASK_GENERAL_INFO:
            response = await self.llm.generate(
                user_message=user_text,
                system_prompt="Trả lời ngắn gọn, tối đa 2-3 câu. Câu trả lời sẽ được đọc thành giọng nói.",
            )
            return response

        return _get_fallback("info")

    async def _safe_tts(self, text: str, voice: str, speed: float) -> bytes:
        """TTS with error handling — returns empty bytes on failure."""
        try:
            return await self.tts.synthesize(text, voice=voice, speed=speed)
        except ProviderError as e:
            logger.warning("pipeline_tts_failed", error=str(e))
            return b""
