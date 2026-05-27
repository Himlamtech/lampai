# AGENTS.md — AI Coding Agent Instructions for Lamp Chạm

## 1. Role

You are an AI software engineering agent working on **Lamp Chạm / LunaLamp**, an AI-integrated smart bedside lamp.

Your job is to implement the **software backend, AI orchestration layer, device protocol, simulator, and tests**. Do not assume physical hardware is always available. All features must be testable through a fake ESP32/device simulator.

---

## 2. Product Context

Lamp Chạm is a screen-free voice-first AI smart lamp. Users speak to the lamp. The system can:

- talk with the user through AI voice,
- answer simple information questions,
- control lamp brightness and modes,
- play relaxing audio,
- respond through light and sound.

The backend is the source of truth for AI orchestration, device state, command routing, logs, and testing.

Ignore any old/mock tech-stack instructions unless explicitly repeated in the current task. Product behavior and use cases are the source of truth.

---

## 3. Engineering Principles

Prioritize:

1. Correctness over cleverness.
2. Small, testable modules.
3. Typed schemas everywhere.
4. Explicit device protocol.
5. Simulator-first development.
6. Clear logs for every state transition.
7. Safe fallback behavior.
8. No hidden global state.
9. No hard-coded secrets.
10. Production-readable code, even for MVP.

Avoid:

- giant service classes,
- untyped dictionaries crossing module boundaries,
- implicit magic behavior,
- LLM calls for simple deterministic commands,
- tight coupling between API routes and providers,
- code that requires real hardware for basic tests,
- adding frontend/mobile/OTA unless requested.

---

## 4. Expected Architecture

Use a modular backend architecture:

```txt
backend/app/
  main.py
  core/
  api/
  domain/
  schemas/
  services/
  repositories/
  infra/
  tests/
simulator/
  fake_device.py
  scenarios/
docs/
```

### Layer Responsibilities

| Layer | Responsibility |
|---|---|
| `api/` | FastAPI routes, request/response boundary only. |
| `schemas/` | Pydantic DTOs for external API and device messages. |
| `domain/` | Intent, command, state, and event models. |
| `services/` | Business logic and orchestration. |
| `repositories/` | Data persistence interface/implementation. |
| `infra/` | WebSocket, database, provider clients, storage. |
| `simulator/` | Fake ESP32 behavior for local testing. |
| `tests/` | Unit, integration, and scenario tests. |

API routes must not directly call OpenAI/Gemini/STT/TTS/device sockets. Route handlers call services.

---

## 5. Core Use Cases

Implement only these MVP use cases unless instructed otherwise:

1. `UC-01 AI Conversation`
2. `UC-02 Information Search`
3. `UC-03 Smart Light Control`
4. `UC-04 Music Playback`

---

## 6. Intent Types

Use these canonical intent values:

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

Never invent new intent names without updating the canonical enum and tests.

---

## 7. Command Types

Use structured command objects for backend-to-device communication.

Canonical command types:

```txt
TURN_ON_LIGHT
TURN_OFF_LIGHT
SET_BRIGHTNESS
CHANGE_LIGHT_MODE
PLAY_MUSIC
STOP_MUSIC
PLAY_TTS_RESPONSE
APPLY_LIGHT_EFFECT
```

All commands must include:

- `messageType`
- `commandId`
- `deviceId`
- `type`
- `payload`
- `timestamp`

Example:

```json
{
  "messageType": "COMMAND",
  "commandId": "cmd_001",
  "deviceId": "lamp_001",
  "type": "SET_BRIGHTNESS",
  "payload": {
    "brightness": 50
  },
  "timestamp": "2026-05-27T10:00:00Z"
}
```

---

## 8. Device State

Use this canonical state shape:

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

Brightness must always be validated as an integer from `0` to `100`.

---

## 9. Backend API Requirements

Implement APIs incrementally. Prefer these routes:

```txt
POST /api/devices/register
POST /api/devices/{device_id}/heartbeat
GET  /api/devices/{device_id}/state
PATCH /api/devices/{device_id}/state
POST /api/devices/{device_id}/commands
GET  /api/devices/{device_id}/commands/{command_id}

POST /api/voice/process-audio
POST /api/voice/process-text
POST /api/ai/intent
POST /api/ai/chat

GET  /api/music/tracks
POST /api/music/play
POST /api/music/stop

GET /api/health
```

For early development, `process-text` is more important than real audio. Implement audio later behind the same pipeline.

---

## 10. Voice Pipeline Rules

The canonical pipeline is:

```txt
Input audio/text
  -> STT if audio
  -> Intent parsing
  -> Route by intent
      -> hardware command path
      -> music path
      -> external info path
      -> chat path
  -> optional TTS
  -> command/response to device
  -> logs
```

Do not call the LLM for simple commands such as “turn on light” if deterministic parsing works.

---

## 11. Simulator-First Rule

Every device-related feature must work with the fake device before real hardware integration.

The fake device must:

- register itself,
- send heartbeat,
- receive commands,
- mutate internal state,
- send ack,
- simulate offline/timeout/failure modes.

Do not write features that can only be tested with physical ESP32.

---

## 12. Provider Abstraction

External providers must be behind interfaces/wrappers:

- `STTService`
- `LLMService`
- `TTSService`
- `ExternalInfoService`
- `MusicService`

Each provider should have mock implementation for tests.

Never put provider SDK calls directly in route handlers.

---

## 13. Error Handling

Use explicit error types or clear error responses.

Expected failure cases:

- device offline,
- command timeout,
- invalid brightness,
- STT failed,
- LLM timeout,
- TTS failed,
- external API failed,
- unsupported intent,
- malformed device ack.

Backend must not crash on these errors. Return structured error responses and log them.

---

## 14. Logging

Use structured logging. Log at least:

- request received,
- intent parsed,
- command created,
- command sent,
- command ack received,
- state updated,
- provider call started/finished,
- error occurred.

Include useful metadata:

- `device_id`,
- `session_id`,
- `command_id`,
- `intent`,
- `latency_ms`,
- `status`,
- `error_code`.

---

## 15. Testing Requirements

For every meaningful feature, add tests.

Minimum required tests:

```txt
test_intent_parser.py
test_command_builder.py
test_device_state.py
test_music_service.py
test_voice_pipeline_text.py
test_fake_device_command_flow.py
```

Scenario tests should cover:

- turn on light,
- set brightness to 30%,
- reject brightness 150%,
- ask weather with mocked provider,
- chat with mocked LLM,
- play rain sound for 15 minutes,
- device offline command failure.

---

## 16. Code Style

Use Python with:

- type hints,
- Pydantic models,
- async functions where IO is involved,
- small focused services,
- dependency injection where practical,
- `.env` config through a settings object.

Do not add unnecessary comments. Use clear names instead.

Prefer readable implementation over over-engineered abstractions.

---

## 17. Security Rules

- Never hard-code API keys.
- Never store AI provider keys in firmware or simulator.
- Use environment variables for secrets.
- Validate device IDs and command payloads.
- Do not log raw secrets.
- Do not assume all devices are trusted.

---

## 18. MVP Prioritization

When uncertain, prioritize in this order:

1. Device simulator.
2. Device state and heartbeat.
3. Text-based intent parsing.
4. Light command dispatch.
5. Music command dispatch.
6. Mock AI chat.
7. Real LLM/STT/TTS integrations.
8. External information tools.
9. Dashboard or OTA only if explicitly requested.

---

## 19. Definition of Done

A task is complete only when:

- Code runs locally.
- Relevant tests pass.
- API/schema is typed.
- Fake device can test the flow if device-related.
- Errors are handled.
- Logs are meaningful.
- No secrets are hard-coded.
- The implementation follows the canonical intent/command/state contracts.
