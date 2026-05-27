import re
from app.domain.intents import IntentType, ParsedIntent
from app.core.logging import get_logger

logger = get_logger("intent_service")


# Vietnamese patterns (evaluated first)
VI_PATTERNS: list[tuple[re.Pattern, IntentType, dict | None]] = [
    # Light on
    (re.compile(r"(bật|mở)\s*(đèn|sáng|light)", re.IGNORECASE), IntentType.TURN_ON_LIGHT, None),
    # Light off
    (re.compile(r"(tắt|đóng)\s*(đèn|sáng|light)", re.IGNORECASE), IntentType.TURN_OFF_LIGHT, None),
    # Set brightness with value
    (re.compile(r"(đặt|chỉnh|set)\s*(độ\s*sáng|brightness)?\s*(?:xuống|lên|về|to)?\s*(\d+)\s*%?", re.IGNORECASE), IntentType.SET_BRIGHTNESS, {"extract": "brightness", "group": 3}),
    # Decrease brightness with value
    (re.compile(r"(giảm|hạ)\s*(độ\s*sáng|brightness)?\s*(?:xuống|về)?\s*(\d+)\s*%?", re.IGNORECASE), IntentType.SET_BRIGHTNESS, {"extract": "brightness", "group": 3}),
    # Increase brightness
    (re.compile(r"(sáng|tăng)\s*(hơn|sáng|lên)", re.IGNORECASE), IntentType.INCREASE_BRIGHTNESS, None),
    (re.compile(r"tăng\s*(độ\s*)?sáng", re.IGNORECASE), IntentType.INCREASE_BRIGHTNESS, None),
    # Decrease brightness
    (re.compile(r"(tối|giảm|dịu)\s*(hơn|sáng|xuống|đi)?", re.IGNORECASE), IntentType.DECREASE_BRIGHTNESS, None),
    (re.compile(r"giảm\s*(độ\s*)?sáng", re.IGNORECASE), IntentType.DECREASE_BRIGHTNESS, None),
    # Change light mode
    (re.compile(r"(chế\s*độ|mode)\s+(.+)", re.IGNORECASE), IntentType.CHANGE_LIGHT_MODE, {"extract": "mode", "group": 2}),
    (re.compile(r"(chuyển|đổi)\s*(sang)?\s*(chế\s*độ|mode)\s+(.+)", re.IGNORECASE), IntentType.CHANGE_LIGHT_MODE, {"extract": "mode", "group": 4}),
    # Play music
    (re.compile(r"(phát|mở|bật)\s*(nhạc|tiếng|âm thanh)\s*(.*)", re.IGNORECASE), IntentType.PLAY_MUSIC, {"extract": "music_type", "group": 3}),
    # Stop music
    (re.compile(r"(dừng|tắt|ngừng|stop)\s*(nhạc|tiếng|âm thanh|music)", re.IGNORECASE), IntentType.STOP_MUSIC, None),
    # Weather
    (re.compile(r"(thời\s*tiết|weather)", re.IGNORECASE), IntentType.ASK_WEATHER, None),
    (re.compile(r"trời\s*.*(nào|sao|thế)", re.IGNORECASE), IntentType.ASK_WEATHER, None),
    # Time
    (re.compile(r"(mấy\s*giờ|bao\s*nhiêu\s*giờ|what\s*time)", re.IGNORECASE), IntentType.ASK_TIME, None),
    (re.compile(r"giờ\s*.*(bao\s*nhiêu|mấy)", re.IGNORECASE), IntentType.ASK_TIME, None),
]

# English patterns (evaluated second)
EN_PATTERNS: list[tuple[re.Pattern, IntentType, dict | None]] = [
    # Light on
    (re.compile(r"turn\s*on\s*(the\s*)?(light|lamp)", re.IGNORECASE), IntentType.TURN_ON_LIGHT, None),
    (re.compile(r"(light|lamp)\s*on", re.IGNORECASE), IntentType.TURN_ON_LIGHT, None),
    # Light off
    (re.compile(r"turn\s*off\s*(the\s*)?(light|lamp)", re.IGNORECASE), IntentType.TURN_OFF_LIGHT, None),
    (re.compile(r"(light|lamp)\s*off", re.IGNORECASE), IntentType.TURN_OFF_LIGHT, None),
    # Set brightness
    (re.compile(r"set\s*(the\s*)?brightness\s*(to\s*)?(\d+)\s*%?", re.IGNORECASE), IntentType.SET_BRIGHTNESS, {"extract": "brightness", "group": 3}),
    (re.compile(r"brightness\s*(to\s*)?(\d+)\s*%?", re.IGNORECASE), IntentType.SET_BRIGHTNESS, {"extract": "brightness", "group": 2}),
    # Increase brightness
    (re.compile(r"(increase|brighter|more\s*light)", re.IGNORECASE), IntentType.INCREASE_BRIGHTNESS, None),
    # Decrease brightness
    (re.compile(r"(decrease|dimmer|less\s*light|dim)", re.IGNORECASE), IntentType.DECREASE_BRIGHTNESS, None),
    # Change mode
    (re.compile(r"(change|switch|set)\s*(to\s*)?(mode\s+)?(.+)\s*mode", re.IGNORECASE), IntentType.CHANGE_LIGHT_MODE, {"extract": "mode", "group": 4}),
    # Play music
    (re.compile(r"play\s*(some\s*)?(.+?)?\s*(music|sound|audio)", re.IGNORECASE), IntentType.PLAY_MUSIC, {"extract": "music_type", "group": 2}),
    # Stop music
    (re.compile(r"stop\s*(the\s*)?(music|sound|audio|playing)", re.IGNORECASE), IntentType.STOP_MUSIC, None),
    # Weather
    (re.compile(r"(weather|forecast)", re.IGNORECASE), IntentType.ASK_WEATHER, None),
    # Time
    (re.compile(r"what\s*(time|hour)", re.IGNORECASE), IntentType.ASK_TIME, None),
]

# Music type normalization
MUSIC_TYPE_MAP = {
    "ngủ": "SLEEP",
    "sleep": "SLEEP",
    "mưa": "RAIN",
    "rain": "RAIN",
    "thiên nhiên": "NATURE",
    "nature": "NATURE",
    "biển": "OCEAN",
    "ocean": "OCEAN",
    "sóng": "OCEAN",
    "wave": "OCEAN",
    "thiền": "MEDITATION",
    "meditation": "MEDITATION",
    "thư giãn": "SLEEP",
    "relax": "SLEEP",
    "relaxing": "SLEEP",
}


def _normalize_music_type(raw: str) -> str:
    raw = raw.strip().lower()
    for key, value in MUSIC_TYPE_MAP.items():
        if key in raw:
            return value
    return "SLEEP"  # default


def _extract_params(match: re.Match, config: dict | None) -> dict:
    if config is None:
        return {}
    extract_name = config["extract"]
    group_idx = config["group"]
    raw_value = match.group(group_idx)
    if raw_value is None:
        return {}
    raw_value = raw_value.strip()
    if not raw_value:
        return {}

    if extract_name == "brightness":
        try:
            value = int(raw_value)
            if 0 <= value <= 100:
                return {"brightness": value}
            else:
                return {"brightness": value, "_invalid": True}
        except ValueError:
            return {"_invalid": True}
    elif extract_name == "music_type":
        return {"music_type": _normalize_music_type(raw_value)}
    elif extract_name == "mode":
        return {"mode": raw_value.upper().replace(" ", "_")}
    return {}


class IntentParser:
    def parse_deterministic(self, text: str) -> ParsedIntent | None:
        text = text.strip()
        if not text:
            return None

        # Try Vietnamese patterns first
        for pattern, intent_type, config in VI_PATTERNS:
            match = pattern.search(text)
            if match:
                params = _extract_params(match, config)
                if params.get("_invalid"):
                    return ParsedIntent(
                        intent=IntentType.UNKNOWN,
                        source="deterministic",
                        error=f"Invalid parameter value extracted from: {text}",
                    )
                return ParsedIntent(
                    intent=intent_type,
                    params=params,
                    source="deterministic",
                )

        # Try English patterns
        for pattern, intent_type, config in EN_PATTERNS:
            match = pattern.search(text)
            if match:
                params = _extract_params(match, config)
                if params.get("_invalid"):
                    return ParsedIntent(
                        intent=IntentType.UNKNOWN,
                        source="deterministic",
                        error=f"Invalid parameter value extracted from: {text}",
                    )
                return ParsedIntent(
                    intent=intent_type,
                    params=params,
                    source="deterministic",
                )

        return None

    async def parse(self, text: str) -> ParsedIntent:
        # Try deterministic first
        result = self.parse_deterministic(text)
        if result is not None:
            logger.info(
                "intent_parsed",
                intent=result.intent.value,
                source="deterministic",
                params=result.params,
            )
            return result

        # Fallback to LLM classification
        try:
            result = await self.parse_with_llm(text)
            logger.info(
                "intent_parsed",
                intent=result.intent.value,
                source="llm",
                params=result.params,
            )
            return result
        except Exception as e:
            logger.error("llm_intent_classification_failed", error=str(e))
            return ParsedIntent(intent=IntentType.UNKNOWN, source="llm", error=str(e))

    async def parse_with_llm(self, text: str) -> ParsedIntent:
        """Classify intent using LLM. Raises on failure."""
        import asyncio
        from openai import AsyncOpenAI
        from app.core.config import settings

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

        system_prompt = """You are an intent classifier for a smart lamp voice assistant.
Classify the user's text into exactly one of these intents:
TURN_ON_LIGHT, TURN_OFF_LIGHT, INCREASE_BRIGHTNESS, DECREASE_BRIGHTNESS, SET_BRIGHTNESS,
CHANGE_LIGHT_MODE, PLAY_MUSIC, STOP_MUSIC, ASK_WEATHER, ASK_TIME, ASK_GENERAL_INFO, CHAT, UNKNOWN

Respond with ONLY a JSON object: {"intent": "INTENT_NAME", "params": {}}
For SET_BRIGHTNESS include: {"intent": "SET_BRIGHTNESS", "params": {"brightness": 50}}
For PLAY_MUSIC include: {"intent": "PLAY_MUSIC", "params": {"music_type": "RAIN"}}
For CHANGE_LIGHT_MODE include: {"intent": "CHANGE_LIGHT_MODE", "params": {"mode": "SLEEP"}}
For other intents, params should be empty: {}"""

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text},
                    ],
                    max_tokens=100,
                    temperature=0,
                ),
                timeout=5.0,
            )

            content = response.choices[0].message.content.strip()
            # Parse JSON response
            import json
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            data = json.loads(content)
            intent_str = data.get("intent", "UNKNOWN")
            params = data.get("params", {})

            try:
                intent_type = IntentType(intent_str)
            except ValueError:
                intent_type = IntentType.UNKNOWN

            return ParsedIntent(intent=intent_type, params=params, source="llm")

        except asyncio.TimeoutError:
            logger.warning("llm_intent_timeout", text=text[:50])
            return ParsedIntent(intent=IntentType.UNKNOWN, source="llm", error="timeout")
        except Exception as e:
            raise
