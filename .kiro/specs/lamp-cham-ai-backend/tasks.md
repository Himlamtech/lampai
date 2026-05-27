# Implementation Plan: Lamp Chạm AI Backend

## Overview

This plan implements the Lamp Chạm AI Backend in 6 phases: Backend Core + Fake Device, Intent + Command Flow, AI Voice Pipeline, External Info + Music Catalog, Web Admin Dashboard + Test Environment, and Deployment. Each task maps to specific requirements and is ordered by dependency.

## Tasks

- [x] 1. Create project skeleton with directory structure (backend/app/main.py, core/, api/, domain/, schemas/, services/, repositories/, infra/), pyproject.toml with all dependencies, .env.example, Pydantic Settings config, structured JSON logging, error types, and FastAPI app initialization with health endpoint
  - Requirements: 14, 16, 18
  - Dependencies: None

- [x] 2. Set up PostgreSQL database with async SQLAlchemy engine, create SQLAlchemy models for devices/commands/conversations/music_catalog/sessions tables, implement migration setup, and add startup connectivity check
  - Requirements: 14, 4
  - Dependencies: 1

- [x] 3. Implement domain models (IntentType enum, ParsedIntent, DeviceCommand, CommandAck, CommandStatus, DeviceStatus, DeviceState) and Pydantic schemas (ConnectionHeaders, HelloMessage, AudioParams, ServerHelloResponse, ListenMessage, STTResult, TTSControl, AbortMessage, ErrorResponse, PaginatedResponse)
  - Requirements: 1, 3, 4, 7
  - Dependencies: 1

- [x] 4. Implement device registration and state management: device repository with async CRUD, device service (register, heartbeat, get_state, update_state), REST endpoints (POST /api/devices/register, POST heartbeat, GET state, PATCH state), brightness validation (0-100), device_id MAC format validation
  - Requirements: 4, 16.5
  - Dependencies: 2, 3

- [ ] 5. Implement WebSocket handler and session management: WebSocketManager (connect, disconnect, send_json, send_binary), SessionManager (create, transition, get, cleanup), /ws endpoint with header validation, hello handshake with timeout (10s) and version check, JSON message dispatch by type, binary frame routing, disconnection cleanup
  - Requirements: 1, 3, 17.4, 17.5
  - Dependencies: 3, 4

- [ ] 6. Implement command dispatcher: command repository with async CRUD, CommandDispatcher service (dispatch, handle_ack, check_timeouts), structured JSON command building, WebSocket delivery, offline device handling (mark FAILED), COMMAND_ACK processing (update command status + device state), 5s timeout check, REST endpoints (POST commands, GET command status)
  - Requirements: 7, 4.5
  - Dependencies: 4, 5

- [ ] 7. Implement heartbeat monitor background task: runs every 30s, marks devices OFFLINE if lastSeenAt > 90s, logs status transitions
  - Requirements: 4.3
  - Dependencies: 4

- [ ] 8. Implement fake device simulator (simulator/fake_device.py): WebSocket connection with headers, hello handshake, periodic heartbeat (30s), command reception with COMMAND_ACK and state update, interactive text mode, configurable failure modes (--failure-mode), structured logging, CLI arguments (--device-id, --backend-url)
  - Requirements: 13
  - Dependencies: 5, 6

- [x] 9. Implement deterministic intent parser: Vietnamese pattern matching (bật/tắt đèn, sáng/tối hơn, chỉnh brightness, chế độ, phát/dừng nhạc, thời tiết, mấy giờ), English patterns (turn on/off, set brightness, play/stop), parameter extraction (brightness 0-100, music_type, light_mode), Vietnamese-first evaluation
  - Requirements: 5.1, 5.3, 5.4, 5.5, 5.7, 5.8, 5.9
  - Dependencies: 3

- [ ] 10. Implement LLM-based intent classification fallback: LangChain prompt for classification, 5s timeout, return UNKNOWN on failure, combined parse() method (deterministic first, then LLM)
  - Requirements: 5.2, 5.6
  - Dependencies: 9

- [ ] 11. Implement smart light control command routing: TURN_ON/OFF_LIGHT, SET_BRIGHTNESS with validation, INCREASE/DECREASE_BRIGHTNESS with clamping (±20, 0-100), CHANGE_LIGHT_MODE with mode payload
  - Requirements: 10
  - Dependencies: 6, 9

- [ ] 12. Implement music playback command routing: PLAY_MUSIC (select track by type, include duration), STOP_MUSIC, fallback to default track when type not found
  - Requirements: 11
  - Dependencies: 6, 9

- [ ] 13. Implement Opus codec integration: OpusEncoder/OpusDecoder classes, decode 16kHz mono 60ms frames to PCM, encode PCM to 24kHz mono 60ms Opus frames, graceful decode error handling, audio buffer with 60s max duration
  - Requirements: 2
  - Dependencies: 1

- [ ] 14. Implement STT service (OpenAI Whisper): abstract STTService interface, OpenAISTTService (PCM to WAV conversion, Whisper API call), language parameter support (vi/en/auto), MockSTTService for testing, retry once on transient errors
  - Requirements: 8.2, 8.4, 8.6
  - Dependencies: 1, 13

- [ ] 15. Implement TTS service (OpenAI TTS-1): abstract TTSService interface, OpenAITTSService (text + voice + speed → audio), convert output to Opus frames for streaming, voice selection and speed support, MockTTSService for testing
  - Requirements: 8.3, 8.4
  - Dependencies: 1, 13

- [ ] 16. Implement LLM service (OpenAI GPT-4o-mini via LangChain): abstract LLMService interface, OpenAILLMService with ChatOpenAI, generate() with system prompt + context + user message, conversation context support (up to 10 turns), MockLLMService for testing
  - Requirements: 8.1, 8.4, 6.4
  - Dependencies: 1

- [ ] 17. Implement voice pipeline orchestration: VoicePipeline class, process_audio() (decode → STT → intent → route → response → TTS → encode), process_text() (skip STT), routing logic (hardware → CommandDispatcher bypass LLM, CHAT → LLM + TTS, info → external tool + TTS), TTS message sequencing (start/sentence_start/stop), per-stage latency tracking, fallback responses for failures
  - Requirements: 6, 17.1, 17.2, 17.3
  - Dependencies: 9, 10, 11, 12, 13, 14, 15, 16

- [ ] 18. Implement conversation logging: conversation repository with async CRUD, store records after each interaction (device_id, session_id, user_text, ai_response, intent, latency_ms, stage_latencies), context retrieval (last 10 turns per session)
  - Requirements: 9.1, 9.4
  - Dependencies: 2, 17

- [ ] 19. Integrate voice pipeline with WebSocket handler: connect listen.start/stop to pipeline, buffer binary frames during listening, send STT/TTS messages to device, stream TTS Opus frames, implement abort handling, add POST /api/voice/process-text endpoint
  - Requirements: 3, 6.2
  - Dependencies: 5, 17

- [ ] 20. Implement external information services: ASK_TIME (current time in configured timezone), ASK_WEATHER (weather API or mock), ASK_GENERAL_INFO (LLM concise answer), summarize to ≤3 sentences, fallback on provider unavailability
  - Requirements: 12
  - Dependencies: 16

- [ ] 21. Implement music catalog with seed data: seed 5 initial tracks (rain, sleep, nature, ocean, meditation), set default track, implement MusicService (get_tracks, select_track, get_default_track)
  - Requirements: 11.4, 11.5
  - Dependencies: 2

- [ ] 22. Implement admin authentication backend: admin_users table, AdminAuthService (create_admin, verify_password with bcrypt, generate/verify JWT), POST /api/admin/login, JWT middleware for /api/admin/* routes (24h expiry), seed initial admin from env vars, max 2 accounts limit
  - Requirements: 19.2, 19.3, 19.6, 19.7
  - Dependencies: 2

- [ ] 23. Implement voice configuration backend: voice_configurations table, VoiceConfigService (get_effective_config with per-device override, update_config), API endpoints (GET/PUT global, GET/PUT/DELETE per-device), validate speed (0.25-4.0) and voice options, integrate with voice pipeline
  - Requirements: 20
  - Dependencies: 2, 22

- [ ] 24. Implement system instructions backend: system_instructions table with version history, InstructionsService (get_effective, update with versioning, get_history), 4 pre-built templates, API endpoints (GET/POST global, GET history, GET templates, GET/POST per-device), integrate with LLM service as system message
  - Requirements: 21
  - Dependencies: 2, 22

- [ ] 25. Implement music catalog management backend: file upload storage (UPLOAD_DIR, UUID-prefixed), audio format validation (mp3/ogg/wav/flac, max 50MB), API endpoints (GET/POST catalog, POST upload, PUT/DELETE track, GET stream, PUT default)
  - Requirements: 22
  - Dependencies: 21, 22

- [ ] 26. Implement conversation history backend: GET /api/admin/conversations (paginated, filterable by device/session/search/date), ILIKE text search, pagination (default 50, max 200), DELETE single and bulk by date range, GET export (JSON/CSV)
  - Requirements: 23
  - Dependencies: 18, 22

- [ ] 27. Implement device management admin backend: GET /api/admin/devices (list with status), GET device details, GET effective config, POST send test command, GET command history, GET /api/admin/dashboard (overview stats)
  - Requirements: 25, 19.4
  - Dependencies: 4, 6, 22

- [ ] 28. Implement admin WebSocket for real-time updates: /ws/admin endpoint with JWT auth, AdminWebSocketManager broadcasting device state changes, command status updates, and new conversations
  - Requirements: 25.3
  - Dependencies: 5, 22

- [ ] 29. Initialize Next.js admin frontend project with TypeScript and Tailwind CSS, implement login page, AuthProvider with JWT management, protected route wrapper, API client library, and static export configuration
  - Requirements: 19.1, 19.2, 19.5
  - Dependencies: 22

- [ ] 30. Implement admin frontend dashboard overview page showing online device count, active connections, recent conversations, with real-time WebSocket updates and responsive layout
  - Requirements: 19.4, 19.5
  - Dependencies: 28, 29

- [ ] 31. Implement admin frontend device management: device list with status indicators, per-device detail page with real-time state, command sending UI, command history table, per-device config page
  - Requirements: 25
  - Dependencies: 27, 29, 30

- [ ] 32. Implement admin frontend voice configuration page: voice selector (6 options), speed slider (0.25-4.0), STT/TTS language dropdowns, global vs per-device toggle, save with feedback
  - Requirements: 20
  - Dependencies: 23, 29

- [ ] 33. Implement admin frontend system instructions page: large text editor, template selector (4 templates), version history viewer, per-device override
  - Requirements: 21
  - Dependencies: 24, 29

- [ ] 34. Implement admin frontend music catalog page: track list, add by URL form, file upload with drag-and-drop, edit metadata modal, delete with confirmation, audio player preview, set-as-default button
  - Requirements: 22
  - Dependencies: 25, 29

- [ ] 35. Implement admin frontend conversation history page: paginated list, search bar, device/date filters, detail view with latencies, single/bulk delete, JSON/CSV export download
  - Requirements: 23
  - Dependencies: 26, 29

- [ ] 36. Implement web-based test environment: /ws/test WebSocket endpoint, virtual test device registration (TE:ST:00:00:00:01), test page with text input, microphone button (MediaRecorder), real-time pipeline viewer (STT/intent/command/response), TTS audio playback, lamp state visualizer
  - Requirements: 24
  - Dependencies: 19, 29

- [ ] 37. Build static frontend and integrate with FastAPI: configure Next.js static export, mount at /admin and /test paths via StaticFiles, verify WebSocket upgrade alongside static serving
  - Requirements: 19.1, 24.1
  - Dependencies: 30, 31, 32, 33, 34, 35, 36

- [ ] 38. Configure Cloudflare Tunnel: set up cloudflared config mapping domain to localhost:8000, verify WSS upgrade through tunnel, document setup in README, test device connection via public URL
  - Requirements: 15
  - Dependencies: 19

- [ ] 39. Set up systemd services: create service files for lampai-backend (uvicorn) and cloudflared, configure auto-restart, log to journald, test graceful shutdown (SIGTERM → close connections → flush DB)
  - Requirements: 17.6
  - Dependencies: 38

- [ ] 40. Run final integration test: full flow with fake device through Cloudflare Tunnel (connect → hello → listen → STT → intent → command → ACK → TTS), verify admin dashboard shows device and conversations, test voice config and system instructions propagation, test web test environment end-to-end
  - Requirements: All
  - Dependencies: 37, 38, 39

## Task Dependency Graph

```json
{
  "waves": [
    [1],
    [2, 3],
    [4, 9, 13, 16],
    [5, 7, 10, 14, 15, 21],
    [6, 11, 12],
    [8, 17, 20, 22],
    [18, 19, 23, 24, 25, 26, 27, 28, 29],
    [30, 31, 32, 33, 34, 35, 36, 38],
    [37, 39],
    [40]
  ]
}
```

## Notes

- Phase 1 (Tasks 1-8): Backend core infrastructure, can be developed and tested entirely with the fake device simulator
- Phase 2 (Tasks 9-12): Intent parsing and command routing, testable via process-text endpoint and fake device
- Phase 3 (Tasks 13-19): Full voice pipeline with real AI providers, requires OpenAI API key
- Phase 4 (Tasks 20-21): External services and music catalog, extends pipeline capabilities
- Phase 5 (Tasks 22-37): Web admin dashboard and test environment, requires all backend APIs to be functional
- Phase 6 (Tasks 38-40): Deployment and final integration testing
- Single uvicorn worker is required because WebSocket sessions are stateful and in-memory
- All AI providers have mock implementations for testing without API keys
- The admin frontend is built as a static Next.js export served by FastAPI (no separate Node.js server in production)
