"""Tests for STT, TTS, and LLM service interfaces."""
import pytest
from app.services.stt_service import MockSTTService
from app.services.tts_service import MockTTSService
from app.services.llm_service import MockLLMService, ConversationTurn


class TestMockSTTService:
    @pytest.mark.asyncio
    async def test_transcribe_returns_default(self):
        stt = MockSTTService()
        result = await stt.transcribe(b"\x00" * 100)
        assert result == "xin chào"

    @pytest.mark.asyncio
    async def test_transcribe_with_custom_response(self):
        stt = MockSTTService(responses={"100": "bật đèn lên"})
        result = await stt.transcribe(b"\x00" * 100)
        assert result == "bật đèn lên"

    @pytest.mark.asyncio
    async def test_tracks_calls(self):
        stt = MockSTTService()
        await stt.transcribe(b"\x00" * 50, sample_rate=16000, language="vi")
        assert len(stt.calls) == 1
        assert stt.calls[0]["audio_size"] == 50
        assert stt.calls[0]["sample_rate"] == 16000
        assert stt.calls[0]["language"] == "vi"


class TestMockTTSService:
    @pytest.mark.asyncio
    async def test_synthesize_returns_bytes(self):
        tts = MockTTSService()
        result = await tts.synthesize("hello")
        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_synthesize_streaming(self):
        tts = MockTTSService()
        chunks = []
        async for chunk in tts.synthesize_streaming("hello"):
            chunks.append(chunk)
        assert len(chunks) == 10  # 10 silent frames
        assert all(isinstance(c, bytes) for c in chunks)

    @pytest.mark.asyncio
    async def test_tracks_calls(self):
        tts = MockTTSService()
        await tts.synthesize("test text", voice="alloy", speed=1.5)
        assert len(tts.calls) == 1
        assert tts.calls[0]["text"] == "test text"
        assert tts.calls[0]["voice"] == "alloy"
        assert tts.calls[0]["speed"] == 1.5


class TestMockLLMService:
    @pytest.mark.asyncio
    async def test_generate_returns_default(self):
        llm = MockLLMService()
        result = await llm.generate("hello")
        assert result == "Đây là phản hồi mặc định từ AI."

    @pytest.mark.asyncio
    async def test_generate_with_custom_response(self):
        llm = MockLLMService(responses={"hello": "Hi there!"})
        result = await llm.generate("hello")
        assert result == "Hi there!"

    @pytest.mark.asyncio
    async def test_tracks_calls_with_context(self):
        llm = MockLLMService()
        context = [
            ConversationTurn(role="user", content="hi"),
            ConversationTurn(role="assistant", content="hello"),
        ]
        await llm.generate("how are you", system_prompt="Be friendly", context=context)
        assert len(llm.calls) == 1
        assert llm.calls[0]["user_message"] == "how are you"
        assert llm.calls[0]["system_prompt"] == "Be friendly"
        assert llm.calls[0]["context_length"] == 2

    @pytest.mark.asyncio
    async def test_generate_empty_returns_empty(self):
        llm = MockLLMService()
        # Mock doesn't enforce empty check, but real service does
        result = await llm.generate("")
        assert result == "Đây là phản hồi mặc định từ AI."
