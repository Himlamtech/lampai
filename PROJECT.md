# PROJECT.md — Lamp Chạm Software Engineering Specification

## 1. Project Identity

**Project name:** Lamp Chạm / LunaLamp — AI Smart Bedside Lamp  
**Product type:** AI-integrated smart bedside lamp / screen-free voice assistant  
**Software role:** Backend AI orchestration, device communication, command routing, state management, testing simulator.

Lamp Chạm is a physical AI companion device. The user interacts with the lamp through voice. The system can understand user commands, control lamp behavior, answer basic questions, play relaxing audio, and respond through both sound and light.

This document intentionally ignores previous mock technology-stack suggestions. The valid source of truth is the product overview, MVP scope, use cases, business rules, and software behavior.

---

## 2. MVP Scope

The MVP must prove four core capabilities:

1. Receive voice or text input from the user/device.
2. Understand whether the input is a hardware command, information request, music request, or free-form chat.
3. Execute lamp/audio behavior through a device command protocol.
4. Return an AI voice response when required.

### In Scope

#### AI Features

- Voice conversation with AI.
- Basic factual/internet information lookup.
- Voice command understanding.
- Simple emotional/light response.
- Short bedtime-style interaction such as story, advice, or relaxation prompt.

#### Hardware-Related Software Features

- Turn lamp on/off.
- Set brightness.
- Increase/decrease brightness.
- Change light mode.
- Play/stop relaxing audio.
- Receive heartbeat and device status.
- Maintain device state.

#### Backend Features

- Device registration.
- Device heartbeat tracking.
- Device state management.
- Intent parsing.
- AI chat orchestration.
- STT/TTS integration points.
- Command dispatch to device.
- Conversation and command logs.
- Fake device simulator for development without hardware.

### Out of Scope for MVP

- Full mobile app.
- Production OTA system.
- Complex user account system.
- Local wake-word engine optimization.
- Local AI model running on ESP32.
- Full smart-home ecosystem integration.
- Payment/subscription system.

---

## 3. Core Actors

| Actor | Responsibility |
|---|---|
| User | Speaks to or controls the lamp. |
| Device/Firmware | Captures audio, controls LED/speaker, sends state, receives commands. |
| Backend Server | Central coordinator for AI, intent, logs, state, and device commands. |
| STT Provider | Converts user audio to text. |
| LLM Provider | Generates AI response or structured reasoning. |
| TTS Provider | Converts response text to audio. |
| External Data Provider | Weather/search/time/general information source. |
| Developer/Admin | Configures, tests, observes, and debugs the system. |
| Fake Device Simulator | Software-only ESP32 substitute for development and integration testing. |

---

## 4. System Boundary

The backend is the source of truth for:

- Device state.
- Intent decisions.
- AI orchestration.
- External API calls.
- Logs and test observability.
- Device command protocol.

The physical device should stay thin:

- Capture input.
- Send audio/text to backend.
- Receive commands.
- Control lamp/speaker.
- Send heartbeat and state updates.

---

## 5. High-Level Architecture

```txt
User
  -> Device / Fake Device
      -> Backend API / WebSocket
          -> Intent Service
          -> STT Service
          -> LLM Service
          -> TTS Service
          -> External Tool Service
          -> Command Dispatcher
          -> State Repository
          -> Log Repository
      <- Command / Audio Response / State Ack
  <- Lamp Light / Speaker Response
```

---

## 6. Recommended Repository Structure

```txt
lamp-cham/
  backend/
    app/
      main.py
      core/
        config.py
        logging.py
        errors.py
      api/
        routes_device.py
        routes_voice.py
        routes_ai.py
        routes_music.py
        routes_health.py
      domain/
        intents.py
        commands.py
        device_state.py
        events.py
      schemas/
        device.py
        voice.py
        ai.py
        music.py
        common.py
      services/
        intent_service.py
        command_service.py
        device_service.py
        voice_pipeline.py
        stt_service.py
        llm_service.py
        tts_service.py
        music_service.py
        external_info_service.py
      repositories/
        device_repository.py
        log_repository.py
        music_repository.py
      infra/
        websocket_manager.py
        mqtt_client.py
        database.py
        storage.py
      tests/
        unit/
        integration/
        scenarios/
    pyproject.toml
    README.md

  simulator/
    fake_device.py
    scenarios/
      turn_on_light.json
      set_brightness.json
      ai_chat.json
      play_music.json
    README.md

  docs/
    PROJECT.md
    API_CONTRACT.md
    USE_CASES.md
    DEVICE_PROTOCOL.md

  AGENTS.md
  docker-compose.yml
  .env.example
```

---

## 7. Use Cases

## UC-01 — AI Conversation

### Goal

Allow the user to naturally talk to the lamp and receive a short voice response with optional light effect.

### Primary Actor

User

### Supporting Actors

Device, Backend, STT Provider, LLM Provider, TTS Provider

### Trigger

User activates the device and speaks a conversational request.

Example:

- “Hôm nay tôi hơi mệt.”
- “Kể tôi nghe một câu chuyện trước khi ngủ.”
- “Nói chuyện với tôi một chút đi.”

### Preconditions

- Device is powered on.
- Microphone is available.
- Backend is reachable.
- STT/LLM/TTS providers are configured or mocked.

### Main Flow

1. User activates the device using push-to-talk or wake trigger.
2. Device records user audio.
3. Device sends audio to backend.
4. Backend transcribes audio to text using STT.
5. Backend parses intent.
6. Backend classifies the request as `CHAT`.
7. Backend sends user text and session context to LLM.
8. LLM generates a concise response.
9. Backend optionally maps response mood to a light effect.
10. Backend converts response text to audio using TTS.
11. Backend sends response audio URL/bytes and light effect command to device.
12. Device plays audio and applies the light effect.
13. Backend stores conversation log.

### Alternative Flows

#### A1 — Text Input Testing Mode

1. Developer sends text directly to `/api/voice/process-text`.
2. Backend skips STT.
3. Flow continues from intent parsing.

#### A2 — TTS Disabled

1. Backend generates text response.
2. Backend returns text only.
3. Fake device prints response in logs.

### Exception Flows

| Case | Behavior |
|---|---|
| STT fails | Return fallback: “Mình chưa nghe rõ, bạn nói lại được không?” |
| LLM timeout | Return safe fallback response. |
| TTS fails | Return text response and error metadata. |
| Device disconnected | Store pending response or mark delivery failed. |

### Acceptance Criteria

- Given a user conversational input, backend returns a response within target latency.
- Conversation is logged with user text, AI response, intent, device ID, and latency.
- Hardware command is not sent unless the intent requires it.

---

## UC-02 — Information Search

### Goal

Allow the user to ask simple factual questions and receive a summarized voice answer.

### Primary Actor

User

### Supporting Actors

Device, Backend, External Data Provider, LLM Provider, TTS Provider

### Trigger

User asks a factual or real-world information question.

Example:

- “Thời tiết hôm nay thế nào?”
- “Bây giờ là mấy giờ?”
- “Giải thích IoT là gì?”
- “Tin tức công nghệ mới nhất là gì?”

### Preconditions

- Backend has internet access or mock provider enabled.
- External tool is configured for the requested information type.

### Main Flow

1. User asks a factual question.
2. Device sends audio to backend.
3. Backend converts speech to text.
4. Backend parses intent as `ASK_WEATHER`, `ASK_TIME`, or `ASK_GENERAL_INFO`.
5. Backend selects the proper tool/provider.
6. Backend calls the external provider.
7. Backend summarizes the result using LLM if needed.
8. Backend converts final answer to speech.
9. Device plays the response.
10. Backend stores interaction log.

### Alternative Flows

#### A1 — Static Knowledge Question

If the question is general knowledge and does not require current data, backend can answer directly using LLM without external search.

#### A2 — Tool Unavailable

If external provider is unavailable, backend returns a transparent fallback message.

### Exception Flows

| Case | Behavior |
|---|---|
| Unsupported topic | Respond that this topic is not supported in MVP. |
| External API timeout | Retry once, then return fallback. |
| Result too long | Summarize to short bedtime-friendly answer. |

### Acceptance Criteria

- Weather/time/general question routes to the correct service.
- Response is short enough for TTS.
- External API errors do not crash the pipeline.

---

## UC-03 — Smart Light Control

### Goal

Allow the user to control lamp state by voice/text command.

### Primary Actor

User

### Supporting Actors

Device, Backend, Fake Device Simulator

### Trigger

User gives a lamp command.

Example:

- “Bật đèn lên.”
- “Tắt đèn đi.”
- “Giảm độ sáng xuống 30%.”
- “Chuyển sang chế độ ngủ.”

### Preconditions

- Device is registered.
- Device or fake device is connected.
- Backend knows current device state.

### Main Flow

1. User speaks a lamp-control command.
2. Device sends audio to backend.
3. Backend converts speech to text.
4. Backend parses intent.
5. Backend identifies one of:
   - `TURN_ON_LIGHT`
   - `TURN_OFF_LIGHT`
   - `SET_BRIGHTNESS`
   - `INCREASE_BRIGHTNESS`
   - `DECREASE_BRIGHTNESS`
   - `CHANGE_LIGHT_MODE`
6. Backend validates command payload.
7. Backend sends structured command to device.
8. Device executes command.
9. Device sends state update/acknowledgement.
10. Backend stores updated state.
11. Backend stores command log.
12. Device gives short confirmation by sound/light.

### Business Rules

| Rule | Description |
|---|---|
| BR-LIGHT-001 | Brightness must be between 0 and 100. |
| BR-LIGHT-002 | “Dịu hơn” decreases brightness by 20 by default. |
| BR-LIGHT-003 | “Sáng hơn” increases brightness by 20 by default. |
| BR-LIGHT-004 | Hardware commands must bypass full LLM chat when rule-based parsing is enough. |
| BR-LIGHT-005 | If device is offline, backend must mark command as failed or pending. |

### Exception Flows

| Case | Behavior |
|---|---|
| Invalid brightness | Clamp or reject with validation error. |
| Device offline | Return device offline response. |
| Command timeout | Mark command as failed. |
| Device already in target state | Return idempotent success message. |

### Acceptance Criteria

- Command is represented as structured JSON.
- Backend can execute this flow against fake device without hardware.
- State after command matches expected output.

---

## UC-04 — Music Playback

### Goal

Allow the user to play or stop relaxing sounds/music through the lamp.

### Primary Actor

User

### Supporting Actors

Device, Backend, Music Source

### Trigger

User requests music or ambient sound.

Example:

- “Phát nhạc ngủ đi.”
- “Mở tiếng mưa.”
- “Phát nhạc thư giãn 15 phút.”
- “Dừng nhạc.”

### Preconditions

- Device speaker is available or simulated.
- Backend has local/static audio catalog or stream URL catalog.

### Main Flow

1. User requests music.
2. Device sends audio/text to backend.
3. Backend parses intent as `PLAY_MUSIC` or `STOP_MUSIC`.
4. Backend extracts music type and optional duration.
5. Backend selects a track from music catalog.
6. Backend sends playback command to device.
7. Device plays audio or fake device simulates playback.
8. Backend updates device state: `isPlayingMusic = true`.
9. If duration exists, backend schedules stop command or sends timer payload.
10. Device applies warm/dim light mode if configured.

### Music Source Policy

For MVP, use a small local/static catalog:

```json
{
  "id": "rain_01",
  "title": "Rain Sound",
  "type": "RAIN",
  "source": "local_or_static_url",
  "durationSeconds": 900
}
```

Do not integrate complex commercial music streaming in MVP unless explicitly required.

### Exception Flows

| Case | Behavior |
|---|---|
| Track not found | Play default relaxing sound. |
| Device offline | Mark command failed. |
| Audio playback failed | Return failure ack and log error. |

### Acceptance Criteria

- Backend supports play/stop command.
- Music catalog can be tested without hardware.
- Optional timer is represented in command payload.

---

## 8. Intent Set

```txt
TURN_ON_LIGHT
TURN_OFF_LIGHT
INCREASE_BRIGHTNESS
DECREASE_BRIGHTNESS
SET_BRIGHTNESS
CHANGE_LIGHT_MODE
PLAY_MUSIC
STOP_MUSIC
ASK_WEATHER
ASK_TIME
ASK_GENERAL_INFO
CHAT
UNKNOWN
```

---

## 9. Device Command Contract

All commands from backend to device must use structured JSON.

### Turn On Light

```json
{
  "messageType": "COMMAND",
  "commandId": "cmd_001",
  "deviceId": "lamp_001",
  "type": "TURN_ON_LIGHT",
  "payload": {},
  "timestamp": "2026-05-27T10:00:00Z"
}
```

### Set Brightness

```json
{
  "messageType": "COMMAND",
  "commandId": "cmd_002",
  "deviceId": "lamp_001",
  "type": "SET_BRIGHTNESS",
  "payload": {
    "brightness": 30
  },
  "timestamp": "2026-05-27T10:00:00Z"
}
```

### Play Music

```json
{
  "messageType": "COMMAND",
  "commandId": "cmd_003",
  "deviceId": "lamp_001",
  "type": "PLAY_MUSIC",
  "payload": {
    "trackId": "rain_01",
    "sourceUrl": "https://example.com/audio/rain_01.mp3",
    "durationSeconds": 900,
    "lightMode": "SLEEP"
  },
  "timestamp": "2026-05-27T10:00:00Z"
}
```

### Device Acknowledgement

```json
{
  "messageType": "COMMAND_ACK",
  "commandId": "cmd_003",
  "deviceId": "lamp_001",
  "status": "SUCCESS",
  "state": {
    "lightPower": true,
    "brightness": 30,
    "mode": "SLEEP",
    "isPlayingMusic": true
  },
  "error": null,
  "timestamp": "2026-05-27T10:00:02Z"
}
```

---

## 10. Device State Model

```json
{
  "deviceId": "lamp_001",
  "status": "ONLINE",
  "lightPower": true,
  "brightness": 70,
  "color": "#FFD27D",
  "mode": "SLEEP",
  "volume": 60,
  "isPlayingMusic": false,
  "lastSeenAt": "2026-05-27T10:00:00Z"
}
```

---

## 11. Backend API Contract

### Device APIs

```txt
POST /api/devices/register
POST /api/devices/{device_id}/heartbeat
GET  /api/devices/{device_id}/state
PATCH /api/devices/{device_id}/state
POST /api/devices/{device_id}/commands
GET  /api/devices/{device_id}/commands/{command_id}
```

### Voice/AI APIs

```txt
POST /api/voice/process-audio
POST /api/voice/process-text
POST /api/ai/intent
POST /api/ai/chat
POST /api/tts
POST /api/stt
```

### Music APIs

```txt
GET  /api/music/tracks
POST /api/music/play
POST /api/music/stop
```

### Observability APIs

```txt
GET /api/health
GET /api/logs/conversations
GET /api/logs/commands
```

---

## 12. Fake Device Simulator Requirements

The simulator must allow backend development without physical hardware.

### Required Behaviors

- Register itself as a device.
- Connect to backend through WebSocket or polling API.
- Send heartbeat every 30 seconds.
- Receive commands.
- Update internal state.
- Send command acknowledgements.
- Simulate failure modes.

### Simulated Failure Modes

```txt
offline
timeout
command_failed
invalid_payload
audio_playback_failed
reconnect
```

### Example Run

```bash
python simulator/fake_device.py --device-id lamp_001 --backend-url http://localhost:8000
```

---

## 13. Logging Requirements

Log every important event with structured fields:

- `event_name`
- `device_id`
- `session_id`
- `command_id`
- `intent`
- `latency_ms`
- `status`
- `error_code`

Example:

```json
{
  "event_name": "command_sent",
  "device_id": "lamp_001",
  "command_id": "cmd_002",
  "intent": "SET_BRIGHTNESS",
  "latency_ms": 124,
  "status": "PENDING"
}
```

---

## 14. Business Rules

1. AI API keys must never be stored in firmware.
2. All AI calls must go through backend.
3. Device must send heartbeat periodically.
4. Hardware commands must be prioritized over full LLM conversation.
5. Brightness must be within `0–100`.
6. The system must not continuously record audio without activation.
7. AI responses must be short enough for TTS.
8. Conversation history must be optional and deletable in future versions.
9. Backend must retry transient STT/LLM/TTS failures where safe.
10. Device offline state must be explicit and visible in logs/state.

---

## 15. Development Phases

### Phase 1 — Backend Core + Fake Device

- Project skeleton.
- Device registration.
- Heartbeat.
- Device state.
- Fake device simulator.
- Command dispatch.

### Phase 2 — Intent + Command Flow

- Text-based intent parser.
- Light command support.
- Music command support.
- Integration tests with fake device.

### Phase 3 — AI Voice Pipeline

- STT integration or mock.
- LLM integration.
- TTS integration or mock.
- Conversation logging.

### Phase 4 — External Info + Music Catalog

- Weather/time/general info tools.
- Static music catalog.
- Play/stop/timer command.

### Phase 5 — Hardware Integration

- Confirm command protocol with firmware developer.
- Replace fake device with real ESP32.
- Test heartbeat, command ack, audio response, and failure cases.

---

## 16. Definition of Done

A software feature is done only when:

- It has typed request/response schemas.
- It works with fake device.
- It has at least unit or integration tests.
- It logs success and failure paths.
- It does not hard-code provider secrets.
- It has documented command/input/output behavior.
- It handles expected errors without crashing.
