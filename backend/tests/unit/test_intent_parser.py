import pytest
from app.services.intent_service import IntentParser
from app.domain.intents import IntentType


@pytest.fixture
def parser():
    return IntentParser()


class TestVietnamesePatterns:
    def test_turn_on_light(self, parser):
        cases = ["bật đèn", "Bật đèn lên", "mở đèn", "Mở sáng"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.TURN_ON_LIGHT
            assert result.source == "deterministic"

    def test_turn_off_light(self, parser):
        cases = ["tắt đèn", "Tắt đèn đi", "tắt sáng"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.TURN_OFF_LIGHT

    def test_set_brightness(self, parser):
        result = parser.parse_deterministic("đặt độ sáng xuống 30%")
        assert result is not None
        assert result.intent == IntentType.SET_BRIGHTNESS
        assert result.params["brightness"] == 30

    def test_set_brightness_no_percent(self, parser):
        result = parser.parse_deterministic("chỉnh độ sáng về 50")
        assert result is not None
        assert result.intent == IntentType.SET_BRIGHTNESS
        assert result.params["brightness"] == 50

    def test_decrease_brightness_with_value(self, parser):
        result = parser.parse_deterministic("giảm độ sáng xuống 20")
        assert result is not None
        assert result.intent == IntentType.SET_BRIGHTNESS
        assert result.params["brightness"] == 20

    def test_increase_brightness(self, parser):
        cases = ["sáng hơn", "tăng sáng", "tăng độ sáng"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.INCREASE_BRIGHTNESS

    def test_decrease_brightness(self, parser):
        cases = ["tối hơn", "dịu hơn", "giảm sáng"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.DECREASE_BRIGHTNESS

    def test_change_light_mode(self, parser):
        result = parser.parse_deterministic("chế độ ngủ")
        assert result is not None
        assert result.intent == IntentType.CHANGE_LIGHT_MODE
        assert result.params["mode"] == "NGỦ"

    def test_change_light_mode_switch(self, parser):
        result = parser.parse_deterministic("chuyển sang chế độ thư giãn")
        assert result is not None
        assert result.intent == IntentType.CHANGE_LIGHT_MODE

    def test_play_music(self, parser):
        result = parser.parse_deterministic("phát nhạc ngủ")
        assert result is not None
        assert result.intent == IntentType.PLAY_MUSIC
        assert result.params["music_type"] == "SLEEP"

    def test_play_rain_sound(self, parser):
        result = parser.parse_deterministic("mở tiếng mưa")
        assert result is not None
        assert result.intent == IntentType.PLAY_MUSIC
        assert result.params["music_type"] == "RAIN"

    def test_stop_music(self, parser):
        cases = ["dừng nhạc", "tắt nhạc", "ngừng nhạc"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.STOP_MUSIC

    def test_ask_weather(self, parser):
        cases = ["thời tiết hôm nay thế nào", "trời hôm nay sao"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.ASK_WEATHER

    def test_ask_time(self, parser):
        cases = ["mấy giờ rồi", "bao nhiêu giờ rồi"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.ASK_TIME


class TestEnglishPatterns:
    def test_turn_on_light(self, parser):
        cases = ["turn on the light", "turn on light", "light on"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.TURN_ON_LIGHT

    def test_turn_off_light(self, parser):
        cases = ["turn off the light", "turn off light", "light off"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.TURN_OFF_LIGHT

    def test_set_brightness(self, parser):
        result = parser.parse_deterministic("set brightness to 75")
        assert result is not None
        assert result.intent == IntentType.SET_BRIGHTNESS
        assert result.params["brightness"] == 75

    def test_set_brightness_percent(self, parser):
        result = parser.parse_deterministic("set the brightness to 40%")
        assert result is not None
        assert result.intent == IntentType.SET_BRIGHTNESS
        assert result.params["brightness"] == 40

    def test_increase_brightness(self, parser):
        cases = ["increase brightness", "brighter", "more light"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.INCREASE_BRIGHTNESS

    def test_decrease_brightness(self, parser):
        cases = ["decrease brightness", "dimmer", "dim"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.DECREASE_BRIGHTNESS

    def test_play_music(self, parser):
        result = parser.parse_deterministic("play rain music")
        assert result is not None
        assert result.intent == IntentType.PLAY_MUSIC
        assert result.params["music_type"] == "RAIN"

    def test_stop_music(self, parser):
        cases = ["stop music", "stop the music", "stop playing"]
        for text in cases:
            result = parser.parse_deterministic(text)
            assert result is not None, f"Failed for: {text}"
            assert result.intent == IntentType.STOP_MUSIC

    def test_ask_weather(self, parser):
        result = parser.parse_deterministic("what's the weather like")
        assert result is not None
        assert result.intent == IntentType.ASK_WEATHER

    def test_ask_time(self, parser):
        result = parser.parse_deterministic("what time is it")
        assert result is not None
        assert result.intent == IntentType.ASK_TIME


class TestEdgeCases:
    def test_empty_string(self, parser):
        result = parser.parse_deterministic("")
        assert result is None

    def test_no_match_returns_none(self, parser):
        result = parser.parse_deterministic("kể tôi nghe một câu chuyện")
        assert result is None

    def test_invalid_brightness_over_100(self, parser):
        result = parser.parse_deterministic("set brightness to 150")
        assert result is not None
        assert result.intent == IntentType.UNKNOWN
        assert result.error is not None

    def test_brightness_boundary_0(self, parser):
        result = parser.parse_deterministic("set brightness to 0")
        assert result is not None
        assert result.intent == IntentType.SET_BRIGHTNESS
        assert result.params["brightness"] == 0

    def test_brightness_boundary_100(self, parser):
        result = parser.parse_deterministic("set brightness to 100")
        assert result is not None
        assert result.intent == IntentType.SET_BRIGHTNESS
        assert result.params["brightness"] == 100

    def test_vietnamese_evaluated_first(self, parser):
        # "bật đèn" should match Vietnamese before any English pattern
        result = parser.parse_deterministic("bật đèn")
        assert result is not None
        assert result.intent == IntentType.TURN_ON_LIGHT
        assert result.source == "deterministic"


class TestAsyncParse:
    @pytest.mark.asyncio
    async def test_deterministic_match_no_llm(self, parser):
        result = await parser.parse("bật đèn")
        assert result.intent == IntentType.TURN_ON_LIGHT
        assert result.source == "deterministic"

    @pytest.mark.asyncio
    async def test_no_match_falls_to_chat(self, parser):
        result = await parser.parse("kể tôi nghe một câu chuyện trước khi ngủ")
        assert result.intent == IntentType.CHAT
