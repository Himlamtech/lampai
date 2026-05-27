"""LLM service abstraction and OpenAI implementation."""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.core.errors import ProviderError

logger = get_logger("llm_service")


@dataclass
class ConversationTurn:
    role: str  # "user" or "assistant"
    content: str


class LLMService(ABC):
    @abstractmethod
    async def generate(
        self,
        user_message: str,
        system_prompt: str = "",
        context: list[ConversationTurn] | None = None,
    ) -> str:
        """Generate a response from the LLM."""
        ...


class OpenAILLMService(LLMService):
    """OpenAI GPT-based LLM service."""

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.model = settings.llm_model
        self.max_context_turns = settings.max_conversation_context

    async def generate(
        self,
        user_message: str,
        system_prompt: str = "",
        context: list[ConversationTurn] | None = None,
    ) -> str:
        """Generate a response using OpenAI chat completion."""
        if not user_message.strip():
            return ""

        messages = []

        # System prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({
                "role": "system",
                "content": self._default_system_prompt(),
            })

        # Conversation context (limited to max turns)
        if context:
            recent = context[-self.max_context_turns:]
            for turn in recent:
                messages.append({"role": turn.role, "content": turn.content})

        # User message
        messages.append({"role": "user", "content": user_message})

        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.7,
                ),
                timeout=10.0,
            )

            content = response.choices[0].message.content.strip()
            logger.info(
                "llm_generation_complete",
                input_length=len(user_message),
                output_length=len(content),
                context_turns=len(context) if context else 0,
            )
            return content

        except asyncio.TimeoutError:
            logger.warning("llm_generation_timeout", input=user_message[:50])
            raise ProviderError("llm", "LLM generation timed out")
        except Exception as e:
            logger.error("llm_generation_failed", error=str(e))
            raise ProviderError("llm", f"LLM generation failed: {e}")

    def _default_system_prompt(self) -> str:
        if settings.language == "vi":
            return (
                "Bạn là trợ lý AI của đèn LunaLamp. "
                "Hãy trả lời ngắn gọn, thân thiện, và hữu ích. "
                "Câu trả lời nên ngắn gọn vì sẽ được đọc thành giọng nói. "
                "Tối đa 2-3 câu cho mỗi phản hồi."
            )
        return (
            "You are the AI assistant of LunaLamp smart bedside lamp. "
            "Keep responses short, friendly, and helpful. "
            "Responses will be read aloud via TTS, so keep them concise. "
            "Maximum 2-3 sentences per response."
        )


class MockLLMService(LLMService):
    """Mock LLM service for testing."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []
        self.default_response = "Đây là phản hồi mặc định từ AI."

    async def generate(
        self,
        user_message: str,
        system_prompt: str = "",
        context: list[ConversationTurn] | None = None,
    ) -> str:
        self.calls.append({
            "user_message": user_message,
            "system_prompt": system_prompt,
            "context_length": len(context) if context else 0,
        })
        return self.responses.get(user_message, self.default_response)
