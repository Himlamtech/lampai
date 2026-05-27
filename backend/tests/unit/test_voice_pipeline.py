"""Tests for voice pipeline orchestration."""
import pytest
from app.services.voice_pipeline import VoicePipeline, _get_confirmation, _get_fallback
from app.services.stt_service import MockSTTService
from app.services.tts_service import MockTTSService
from app.services.llm_service import MockLLMService
from app.services.intent_service import IntentParser
from app.domain.intents import IntentType


@pytest.fixture
def pipeline():
    return VoicePipeline(
        stt_service=MockSTTService(responses={"100": "bật đèn lên"}),
        tts_service=MockTTSService(),
        llm_service=MockLLMService(responses={
            "kể chuyện đi": "Ngày xưa có một chú thỏ...",
            "hôm nay tôi mệt": "Bạn nên nghỉ ngơi sớm nhé.",
        }),
        intent_parser=IntentParser(),
    )


class TestVoicePipelineText:
    @pytest.mark.asyncio
    async def test_hardware_intent_bypasses_llm(self, pipeline):
        """Hardware commands should not call LLM."""
        result = await pipeline.process_text(
            text="bật đèn lên",
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        assert result.intent.intent == IntentType.TURN_ON_LIGHT
        assert result.intent.source == "deterministic"
        assert result.command_sent is True
        assert "Đã bật đèn" in result.ai_response
        assert result.tts_audio != b""
        # LLM should NOT have been called
        assert len(pipeline.llm.calls) == 0

    @pytest.mark.asyncio
    async def test_set_brightness_extracts_value(self, pipeline):
        result = await pipeline.process_text(
            text="đặt độ sáng xuống 30%",
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        assert result.intent.intent == IntentType.SET_BRIGHTNESS
        assert result.intent.params["brightness"] == 30
        assert result.command_sent is True

    @pytest.mark.asyncio
    async def test_chat_intent_calls_llm(self, pipeline):
        """Chat intents should call LLM for response."""
        result = await pipeline.process_text(
            text="kể chuyện đi",
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        # This won't match deterministic patterns, so goes to LLM for classification
        # Then LLM generates response
        assert result.ai_response != ""
        assert result.tts_audio != b""

    @pytest.mark.asyncio
    async def test_ask_time_returns_time(self, pipeline):
        result = await pipeline.process_text(
            text="mấy giờ rồi",
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        assert result.intent.intent == IntentType.ASK_TIME
        assert "giờ" in result.ai_response or ":" in result.ai_response

    @pytest.mark.asyncio
    async def test_play_music_extracts_type(self, pipeline):
        result = await pipeline.process_text(
            text="phát nhạc mưa",
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        assert result.intent.intent == IntentType.PLAY_MUSIC
        assert result.intent.params["music_type"] == "RAIN"
        assert result.command_sent is True

    @pytest.mark.asyncio
    async def test_stop_music(self, pipeline):
        result = await pipeline.process_text(
            text="dừng nhạc",
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        assert result.intent.intent == IntentType.STOP_MUSIC
        assert result.command_sent is True

    @pytest.mark.asyncio
    async def test_stage_latencies_tracked(self, pipeline):
        result = await pipeline.process_text(
            text="bật đèn",
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        assert "intent" in result.stage_latencies
        assert "tts" in result.stage_latencies
        assert result.total_latency_ms >= 0

    @pytest.mark.asyncio
    async def test_empty_text_returns_fallback(self, pipeline):
        result = await pipeline.process_text(
            text="",
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        # Empty text won't match patterns, goes to LLM which returns default
        assert result.ai_response != ""


class TestVoicePipelineAudio:
    @pytest.mark.asyncio
    async def test_process_audio_with_stt(self, pipeline):
        """Audio processing should go through STT first."""
        result = await pipeline.process_audio(
            audio_buffer=b"\x00" * 100,  # MockSTT maps size "100" to "bật đèn lên"
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        assert result.user_text == "bật đèn lên"
        assert result.intent.intent == IntentType.TURN_ON_LIGHT
        assert "stt" in result.stage_latencies

    @pytest.mark.asyncio
    async def test_stt_failure_returns_fallback(self):
        """STT failure should return fallback message."""
        from app.services.stt_service import STTService
        from app.core.errors import ProviderError

        class FailingSTT(STTService):
            async def transcribe(self, audio, sample_rate=16000, language="vi"):
                raise ProviderError("stt", "Service unavailable")

        pipeline = VoicePipeline(
            stt_service=FailingSTT(),
            tts_service=MockTTSService(),
            llm_service=MockLLMService(),
        )

        result = await pipeline.process_audio(
            audio_buffer=b"\x00" * 100,
            device_id="AA:BB:CC:DD:EE:FF",
            session_id="test-session",
        )
        assert result.error == "stt_failed"
        assert "nghe rõ" in result.ai_response or "catch" in result.ai_response


class TestConfirmations:
    def test_vi_confirmations(self):
        from app.core.config import settings
        original = settings.language
        settings.language = "vi"
        assert "bật đèn" in _get_confirmation(IntentType.TURN_ON_LIGHT).lower()
        assert "tắt đèn" in _get_confirmation(IntentType.TURN_OFF_LIGHT).lower()
        settings.language = original

    def test_fallback_messages(self):
        from app.core.config import settings
        original = settings.language
        settings.language = "vi"
        assert "nghe rõ" in _get_fallback("stt")
        settings.language = "en"
        assert "catch" in _get_fallback("stt").lower()
        settings.language = original
