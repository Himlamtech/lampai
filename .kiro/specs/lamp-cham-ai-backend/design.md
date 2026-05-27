# Design Document: Lamp Chạm AI Backend

## Overview

The Lamp Chạm AI Backend is a Python/FastAPI WebSocket server implementing the XiaoZhi ESP32 communication protocol. It serves as the central AI orchestration layer for the LunaLamp smart bedside lamp, handling:

- Real-time bidirectional WebSocket communication with ESP32 devices
- Voice processing pipeline (STT → Intent → Routing → Response → TTS)
- Deterministic + LLM-based intent classification
- Device command dispatch and acknowledgement tracking
- Device state management with PostgreSQL persistence
- Conversation history and structured logging

The system is self-hosted on a Linux server (i7-12700F, 32GB RAM, RTX 4090) and exposed to the internet via Cloudflare Tunnel.

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| FastAPI + WebSocket | Native async support, Pydantic integration, WebSocket first-class |
| LangChain for LLM orchestration | Provider abstraction, chain composition, easy swap between models |
| Deterministic intent parsing first | Avoid LLM latency/cost for simple hardware commands |
| PostgreSQL with async (asyncpg + SQLAlchemy) | ACID guarantees, async non-blocking, rich query support |
| Opus codec (opuslib) | Protocol-mandated, low-latency, good compression for voice |
| Session-based state machine | Clean lifecycle management per device connection |
| Pydantic Settings for config | Type-safe env loading, validation at startup |

---

## Architecture

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Public Internet                               │
│                    (ESP32 devices connect here)                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ WSS (port 443)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Cloudflare Tunnel (cloudflared)                   │
│                 Maps domain → localhost:8000                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ WS (port 8000)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                             │
│                                                                        │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────────┐ │
│  │  HTTP API   │  │  WebSocket   │  │     Background Tasks         │ │
│  │  (REST)     │  │  Handler     │  │  (heartbeat monitor, timers) │ │
│  └──────┬──────┘  └──────┬───────┘  └──────────────┬──────────────┘ │
│         │                 │                          │                 │
│         ▼                 ▼                          ▼                 │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                      Service Layer                              │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │  │
│  │  │  Voice   │ │  Intent  │ │  Device  │ │    Command       │  │  │
│  │  │ Pipeline │ │  Parser  │ │  Service │ │   Dispatcher     │  │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬──────────┘  │  │
│  │       │             │            │               │              │  │
│  │  ┌────┴─────────────┴────────────┴───────────────┴──────────┐  │  │
│  │  │              AI Provider Abstraction Layer                 │  │  │
│  │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐   │  │  │
│  │  │  │   STT   │  │   LLM   │  │   TTS   │  │  External │   │  │  │
│  │  │  │ Service │  │ Service │  │ Service │  │   Info    │   │  │  │
│  │  │  └─────────┘  └─────────┘  └─────────┘  └───────────┘   │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    Infrastructure Layer                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │  │
│  │  │  WebSocket   │  │   Database   │  │    Opus Codec       │  │  │
│  │  │   Manager    │  │  (asyncpg)   │  │   (encode/decode)   │  │  │
│  │  └──────────────┘  └──────────────┘  └─────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      PostgreSQL 16                                     │
│  devices │ commands │ conversations │ music_catalog │ sessions        │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Interaction Diagram

```mermaid
graph TD
    Device[ESP32 Device / Simulator] -->|WebSocket| WSHandler[WebSocket Handler]
    
    WSHandler -->|Binary frames| OpusCodec[Opus Codec]
    WSHandler -->|JSON messages| MsgDispatcher[Message Dispatcher]
    
    OpusCodec -->|PCM audio| VoicePipeline[Voice Pipeline]
    MsgDispatcher -->|listen/abort/mcp| SessionManager[Session Manager]
    
    VoicePipeline -->|audio| STTService[STT Service]
    STTService -->|text| IntentParser[Intent Parser]
    IntentParser -->|intent + params| Router[Intent Router]
    
    Router -->|hardware intent| CmdDispatcher[Command Dispatcher]
    Router -->|chat intent| LLMService[LLM Service]
    Router -->|info intent| ExternalInfo[External Info Service]
    Router -->|music intent| MusicService[Music Service]
    
    LLMService -->|response text| TTSService[TTS Service]
    ExternalInfo -->|info text| TTSService
    CmdDispatcher -->|confirmation| TTSService
    
    TTSService -->|opus frames| WSHandler
    CmdDispatcher -->|command JSON| WSHandler
    
    SessionManager -->|state| DeviceService[Device Service]
    DeviceService -->|CRUD| DeviceRepo[Device Repository]
    CmdDispatcher -->|log| CommandRepo[Command Repository]
    VoicePipeline -->|log| ConversationRepo[Conversation Repository]
    
    DeviceRepo -->|async| DB[(PostgreSQL)]
    CommandRepo -->|async| DB
    ConversationRepo -->|async| DB
```

---

## Components and Interfaces

### 1. WebSocket Handler (`infra/websocket_manager.py`)

Manages WebSocket connections, authentication, and frame routing.

```python
class WebSocketManager:
    async def connect(self, websocket: WebSocket, headers: ConnectionHeaders) -> Session
    async def disconnect(self, session_id: str) -> None
    async def send_json(self, session_id: str, message: dict) -> None
    async def send_binary(self, session_id: str, data: bytes) -> None
    def get_active_sessions(self) -> list[Session]
    def get_session_by_device(self, device_id: str) -> Session | None
```

### 2. Session Manager (`services/session_manager.py`)

Tracks session lifecycle and state machine transitions.

```python
class SessionManager:
    async def create_session(self, device_id: str, hello_msg: HelloMessage) -> Session
    async def transition(self, session_id: str, new_state: SessionState) -> None
    async def get_session(self, session_id: str) -> Session | None
    async def cleanup_session(self, session_id: str) -> None
```

### 3. Voice Pipeline (`services/voice_pipeline.py`)

Orchestrates the full voice processing chain.

```python
class VoicePipeline:
    async def process_audio(self, session: Session, audio_buffer: AudioBuffer) -> PipelineResult
    async def process_text(self, session: Session, text: str) -> PipelineResult
```

### 4. Intent Parser (`services/intent_service.py`)

Classifies user input into canonical intents.

```python
class IntentParser:
    def parse_deterministic(self, text: str, language: str) -> ParsedIntent | None
    async def parse_with_llm(self, text: str) -> ParsedIntent
    async def parse(self, text: str) -> ParsedIntent
```

### 5. Command Dispatcher (`services/command_service.py`)

Builds and sends structured commands to devices.

```python
class CommandDispatcher:
    async def dispatch(self, device_id: str, intent: ParsedIntent) -> CommandResult
    async def handle_ack(self, ack: CommandAck) -> None
    async def check_timeouts(self) -> None
```

### 6. Device Service (`services/device_service.py`)

Manages device registration, state, and heartbeat.

```python
class DeviceService:
    async def register(self, device_id: str) -> DeviceState
    async def heartbeat(self, device_id: str) -> None
    async def get_state(self, device_id: str) -> DeviceState
    async def update_state(self, device_id: str, updates: dict) -> DeviceState
    async def mark_offline_stale_devices(self) -> None
```

### 7. AI Provider Interfaces

```python
class STTService(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, sample_rate: int, language: str) -> str

class LLMService(ABC):
    @abstractmethod
    async def generate(self, prompt: str, context: list[ConversationTurn]) -> str
    @abstractmethod
    async def classify_intent(self, text: str) -> ParsedIntent

class TTSService(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str) -> AsyncIterator[bytes]
```

### 8. Music Service (`services/music_service.py`)

```python
class MusicService:
    async def get_tracks(self, music_type: str | None = None) -> list[MusicTrack]
    async def select_track(self, music_type: str) -> MusicTrack
    async def get_default_track(self) -> MusicTrack
```

---

## Data Models

### PostgreSQL Schema

```sql
-- Device registry and state
CREATE TABLE devices (
    device_id       VARCHAR(17) PRIMARY KEY,  -- MAC address format XX:XX:XX:XX:XX:XX
    client_id       UUID,
    status          VARCHAR(10) NOT NULL DEFAULT 'OFFLINE',  -- ONLINE, OFFLINE
    light_power     BOOLEAN NOT NULL DEFAULT false,
    brightness      INTEGER NOT NULL DEFAULT 50 CHECK (brightness >= 0 AND brightness <= 100),
    color           VARCHAR(7) NOT NULL DEFAULT '#FFD27D',   -- hex color
    mode            VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    volume          INTEGER NOT NULL DEFAULT 60 CHECK (volume >= 0 AND volume <= 100),
    is_playing_music BOOLEAN NOT NULL DEFAULT false,
    last_seen_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Command log with status tracking
CREATE TABLE commands (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    command_id      VARCHAR(64) NOT NULL UNIQUE,
    device_id       VARCHAR(17) NOT NULL REFERENCES devices(device_id),
    type            VARCHAR(30) NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(15) NOT NULL DEFAULT 'PENDING',  -- PENDING, SENT, SUCCESS, FAILED, TIMED_OUT
    failure_reason  VARCHAR(100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at         TIMESTAMPTZ,
    acked_at        TIMESTAMPTZ
);

CREATE INDEX idx_commands_device_id ON commands(device_id);
CREATE INDEX idx_commands_status ON commands(status);

-- Conversation history
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id       VARCHAR(17) NOT NULL REFERENCES devices(device_id),
    session_id      VARCHAR(64) NOT NULL,
    user_text       TEXT NOT NULL,
    ai_response     TEXT,
    intent          VARCHAR(30) NOT NULL,
    latency_ms      INTEGER,
    stage_latencies JSONB,  -- {"stt": 120, "intent": 15, "llm": 800, "tts": 200}
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversations_device_session ON conversations(device_id, session_id);
CREATE INDEX idx_conversations_created_at ON conversations(created_at);

-- Music catalog
CREATE TABLE music_catalog (
    id              VARCHAR(30) PRIMARY KEY,
    title           VARCHAR(100) NOT NULL,
    type            VARCHAR(30) NOT NULL,  -- RAIN, SLEEP, NATURE, OCEAN, MEDITATION
    source_url      TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    is_default      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_music_catalog_type ON music_catalog(type);

-- Active sessions (in-memory primary, DB for recovery)
CREATE TABLE sessions (
    session_id      VARCHAR(64) PRIMARY KEY,
    device_id       VARCHAR(17) NOT NULL REFERENCES devices(device_id),
    state           VARCHAR(20) NOT NULL DEFAULT 'connected',  -- connected, listening, processing, speaking, idle
    mode            VARCHAR(10),  -- auto, manual, realtime
    protocol_version INTEGER NOT NULL DEFAULT 1,
    connected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Key Pydantic Schemas

```python
# schemas/device.py
class ConnectionHeaders(BaseModel):
    authorization: str  # "Bearer <token>"
    protocol_version: int
    device_id: str  # MAC address
    client_id: str  # UUID

class HelloMessage(BaseModel):
    type: Literal["hello"]
    version: int
    transport: Literal["websocket"]
    audio_params: AudioParams
    features: dict[str, bool] = {}

class AudioParams(BaseModel):
    format: Literal["opus"]
    sample_rate: int  # 16000 (device up) or 24000 (server down)
    channels: Literal[1]
    frame_duration: int = 60  # ms

class ServerHelloResponse(BaseModel):
    type: Literal["hello"] = "hello"
    transport: Literal["websocket"] = "websocket"
    session_id: str
    audio_params: AudioParams

# schemas/voice.py
class ListenMessage(BaseModel):
    session_id: str
    type: Literal["listen"]
    state: Literal["start", "stop", "detect"]
    mode: Literal["auto", "manual", "realtime"] | None = None
    text: str | None = None  # wake word text for "detect"

class STTResult(BaseModel):
    session_id: str
    type: Literal["stt"] = "stt"
    text: str

class TTSControl(BaseModel):
    session_id: str
    type: Literal["tts"] = "tts"
    state: Literal["start", "stop", "sentence_start"]
    text: str | None = None  # sentence text for "sentence_start"

class AbortMessage(BaseModel):
    session_id: str
    type: Literal["abort"]
    reason: str | None = None

# domain/intents.py
class IntentType(str, Enum):
    TURN_ON_LIGHT = "TURN_ON_LIGHT"
    TURN_OFF_LIGHT = "TURN_OFF_LIGHT"
    INCREASE_BRIGHTNESS = "INCREASE_BRIGHTNESS"
    DECREASE_BRIGHTNESS = "DECREASE_BRIGHTNESS"
    SET_BRIGHTNESS = "SET_BRIGHTNESS"
    CHANGE_LIGHT_MODE = "CHANGE_LIGHT_MODE"
    PLAY_MUSIC = "PLAY_MUSIC"
    STOP_MUSIC = "STOP_MUSIC"
    ASK_WEATHER = "ASK_WEATHER"
    ASK_TIME = "ASK_TIME"
    ASK_GENERAL_INFO = "ASK_GENERAL_INFO"
    CHAT = "CHAT"
    UNKNOWN = "UNKNOWN"

class ParsedIntent(BaseModel):
    intent: IntentType
    confidence: float = 1.0
    params: dict = {}  # e.g., {"brightness": 50}, {"music_type": "rain"}
    source: Literal["deterministic", "llm"] = "deterministic"
    error: str | None = None

# domain/commands.py
class DeviceCommand(BaseModel):
    messageType: Literal["COMMAND"] = "COMMAND"
    commandId: str
    deviceId: str
    type: str
    payload: dict
    timestamp: str  # ISO 8601

class CommandAck(BaseModel):
    messageType: Literal["COMMAND_ACK"]
    commandId: str
    deviceId: str
    status: Literal["SUCCESS", "FAILED"]
    state: dict | None = None
    error: str | None = None
    timestamp: str

class CommandStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"

# domain/device_state.py
class DeviceStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"

class DeviceState(BaseModel):
    deviceId: str
    status: DeviceStatus = DeviceStatus.OFFLINE
    lightPower: bool = False
    brightness: int = Field(default=50, ge=0, le=100)
    color: str = "#FFD27D"
    mode: str = "NORMAL"
    volume: int = Field(default=60, ge=0, le=100)
    isPlayingMusic: bool = False
    lastSeenAt: datetime | None = None
```

---

## WebSocket Session Lifecycle and State Machine

```mermaid
stateDiagram-v2
    [*] --> Connecting: Device opens WebSocket
    
    Connecting --> Authenticating: Headers received
    Authenticating --> Rejected: Invalid auth
    Rejected --> [*]: Connection closed
    
    Authenticating --> WaitingHello: Auth valid, upgrade complete
    WaitingHello --> Rejected: Hello timeout (10s)
    WaitingHello --> Rejected: Invalid hello version
    
    WaitingHello --> Idle: Valid hello received, server hello sent
    
    Idle --> Listening: listen.start received
    Idle --> [*]: Device disconnects
    
    Listening --> Processing: listen.stop received OR 60s buffer full
    Listening --> Idle: abort received
    Listening --> [*]: Device disconnects
    
    Processing --> Speaking: TTS start
    Processing --> Idle: No TTS needed (text-only response)
    Processing --> Idle: abort received
    Processing --> [*]: Device disconnects
    
    Speaking --> Listening: TTS stop (auto mode)
    Speaking --> Idle: TTS stop (manual mode)
    Speaking --> Idle: abort received
    Speaking --> [*]: Device disconnects
```

### Session States

| State | Description | Accepts Audio | Sends Audio |
|-------|-------------|:---:|:---:|
| Connecting | TCP handshake in progress | ✗ | ✗ |
| WaitingHello | Waiting for device hello message | ✗ | ✗ |
| Idle | Session active, no voice interaction | ✗ | ✗ |
| Listening | Receiving and buffering device audio | ✓ | ✗ |
| Processing | Running STT → Intent → LLM/Command pipeline | ✗ | ✗ |
| Speaking | Streaming TTS audio to device | ✗ | ✓ |

---

## Voice Pipeline Sequence Diagram

```mermaid
sequenceDiagram
    participant D as Device
    participant WS as WebSocket Handler
    participant SM as Session Manager
    participant VP as Voice Pipeline
    participant STT as STT Service
    participant IP as Intent Parser
    participant R as Router
    participant LLM as LLM Service
    participant CMD as Command Dispatcher
    participant TTS as TTS Service
    participant DB as PostgreSQL

    D->>WS: listen {state: "start", mode: "auto"}
    WS->>SM: transition(session, LISTENING)
    
    loop Audio streaming
        D->>WS: Binary Opus frames
        WS->>VP: buffer_audio(frame)
    end
    
    D->>WS: listen {state: "stop"}
    WS->>VP: finalize_audio()
    SM->>SM: transition(session, PROCESSING)
    
    VP->>STT: transcribe(audio_buffer)
    STT-->>VP: "bật đèn lên"
    VP->>WS: stt {text: "bật đèn lên"}
    WS->>D: STT result
    
    VP->>IP: parse("bật đèn lên")
    IP-->>VP: ParsedIntent(TURN_ON_LIGHT, source=deterministic)
    
    VP->>R: route(intent)
    R->>CMD: dispatch(device_id, TURN_ON_LIGHT)
    CMD->>DB: store command (PENDING)
    CMD->>WS: send command to device
    WS->>D: COMMAND {type: TURN_ON_LIGHT}
    CMD->>DB: update status (SENT)
    
    R->>TTS: synthesize("Đã bật đèn")
    SM->>SM: transition(session, SPEAKING)
    VP->>WS: tts {state: "start"}
    WS->>D: TTS start
    
    loop TTS frames
        TTS-->>VP: Opus frame
        VP->>WS: Binary frame
        WS->>D: Opus audio
    end
    
    VP->>WS: tts {state: "stop"}
    WS->>D: TTS stop
    SM->>SM: transition(session, IDLE)
    
    D->>WS: COMMAND_ACK {status: SUCCESS}
    WS->>CMD: handle_ack(ack)
    CMD->>DB: update status (SUCCESS)
    CMD->>DB: update device state
    
    VP->>DB: store conversation log
```

---

## Intent Parsing Flow

```mermaid
flowchart TD
    A[User Text Input] --> B{Match Vietnamese Pattern?}
    B -->|Yes| C[Return Intent + Params]
    B -->|No| D{Match English Pattern?}
    D -->|Yes| C
    D -->|No| E{LLM Available?}
    E -->|No| F[Return UNKNOWN + log error]
    E -->|Yes| G[Call LLM classify_intent]
    G --> H{LLM Response Valid?}
    H -->|Yes| I[Return Intent from LLM]
    H -->|No/Timeout| F
    
    C --> J[Extract Parameters]
    J --> K{Params Valid?}
    K -->|Yes| L[Return ParsedIntent]
    K -->|No| F
```

### Deterministic Pattern Examples

| Language | Pattern | Intent | Extracted Params |
|----------|---------|--------|-----------------|
| VI | `bật đèn`, `mở đèn` | TURN_ON_LIGHT | — |
| VI | `tắt đèn` | TURN_OFF_LIGHT | — |
| VI | `(đặt\|chỉnh) .* (\d+)%?` | SET_BRIGHTNESS | brightness: int |
| VI | `sáng hơn`, `tăng sáng` | INCREASE_BRIGHTNESS | — |
| VI | `tối hơn`, `giảm sáng`, `dịu hơn` | DECREASE_BRIGHTNESS | — |
| VI | `chế độ (.+)` | CHANGE_LIGHT_MODE | mode: str |
| VI | `phát nhạc (.*)`, `mở nhạc (.*)` | PLAY_MUSIC | music_type: str |
| VI | `dừng nhạc`, `tắt nhạc` | STOP_MUSIC | — |
| VI | `thời tiết`, `trời .* nào` | ASK_WEATHER | — |
| VI | `mấy giờ`, `giờ .* bao nhiêu` | ASK_TIME | — |
| EN | `turn on (the )?light` | TURN_ON_LIGHT | — |
| EN | `turn off (the )?light` | TURN_OFF_LIGHT | — |
| EN | `set brightness (to )?(\d+)` | SET_BRIGHTNESS | brightness: int |
| EN | `play .* music`, `play .* sound` | PLAY_MUSIC | music_type: str |

---

## API Endpoint Specifications

### Device Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/devices/register` | Register a new device |
| POST | `/api/devices/{device_id}/heartbeat` | Update device heartbeat |
| GET | `/api/devices/{device_id}/state` | Get current device state |
| PATCH | `/api/devices/{device_id}/state` | Update device state |
| POST | `/api/devices/{device_id}/commands` | Send command to device |
| GET | `/api/devices/{device_id}/commands/{command_id}` | Get command status |

### Voice/AI

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/voice/process-text` | Process text through voice pipeline (skip STT) |
| POST | `/api/voice/process-audio` | Process audio through full pipeline |
| POST | `/api/ai/intent` | Parse intent from text (standalone) |
| POST | `/api/ai/chat` | Direct chat with LLM |

### Music

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/music/tracks` | List music catalog |
| POST | `/api/music/play` | Play music on device |
| POST | `/api/music/stop` | Stop music on device |

### WebSocket

| Path | Description |
|------|-------------|
| `/ws` | XiaoZhi protocol WebSocket endpoint |

### Observability

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check with DB and WS status |

### Health Response Schema

```json
{
  "status": "healthy",
  "database": "connected",
  "active_connections": 3,
  "uptime_seconds": 12345,
  "version": "0.1.0"
}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: WebSocket Header Validation

*For any* set of WebSocket connection headers, the Backend_Server SHALL accept the connection if and only if all four headers (Authorization, Protocol-Version, Device-Id, Client-Id) are present, non-empty, and the Authorization token is recognized. Any other combination SHALL result in rejection.

**Validates: Requirements 1.1, 1.2, 16.4**

### Property 2: Hello Handshake Response Completeness

*For any* valid hello message from a device (containing type "hello", valid version, transport "websocket", and complete audio_params), the server response SHALL always contain type "hello", transport "websocket", a non-empty session_id string, and valid audio_params with format, sample_rate, channels, and frame_duration fields.

**Validates: Requirements 1.3**

### Property 3: Session State Guards Binary Frame Processing

*For any* session that is NOT in "listening" state, all received binary WebSocket frames SHALL be discarded without processing or error. Only sessions in "listening" state SHALL buffer incoming binary frames.

**Validates: Requirements 2.6, 2.3**

### Property 4: Listen Message State Transitions

*For any* valid listen message with state "start" and mode in {"auto", "manual", "realtime"}, the session SHALL transition to "listening" state. For any abort message, the session SHALL transition to "idle" state regardless of current state.

**Validates: Requirements 3.1, 3.3**

### Property 5: TTS Message Sequencing

*For any* TTS response consisting of N sentences (N ≥ 1), the server SHALL send messages in this exact order: one tts{state:"start"}, then for each sentence one tts{state:"sentence_start", text:...} followed by binary audio frames, and finally one tts{state:"stop"}. No audio frames SHALL appear before the first "start" or after the final "stop".

**Validates: Requirements 3.5, 3.6**

### Property 6: STT Result Message Format

*For any* completed STT transcription producing text T, the server SHALL send a JSON message to the device containing type "stt", the correct session_id, and text field equal to T (truncated to 4096 characters maximum).

**Validates: Requirements 3.4**

### Property 7: Device State Persistence Round-Trip

*For any* valid device state (with brightness 0-100, valid status, valid color hex), persisting to PostgreSQL and then retrieving by device_id SHALL produce an equivalent state object.

**Validates: Requirements 4.4, 4.1**

### Property 8: Brightness Validation Invariant

*For any* integer value V, the brightness validation SHALL accept V if and only if 0 ≤ V ≤ 100. Values outside this range SHALL be rejected with a validation error.

**Validates: Requirements 4.6, 10.5**

### Property 9: Heartbeat Updates Timestamp

*For any* registered device that sends a heartbeat, the stored lastSeenAt SHALL be updated to a value within 1 second of the current server time, and the device status SHALL be set to ONLINE.

**Validates: Requirements 4.2**

### Property 10: Command ACK Updates State

*For any* valid COMMAND_ACK message containing state fields, the stored device state SHALL be updated to match the acknowledged values, and the command status SHALL be updated to match the ack status field (SUCCESS or FAILED).

**Validates: Requirements 4.5, 7.4**

### Property 11: Deterministic Intent Parsing Without LLM

*For any* text input that matches a known deterministic pattern (in Vietnamese or English), the Intent_Parser SHALL return the correct intent type and extracted parameters with source="deterministic", and the LLM_Service SHALL NOT be called.

**Validates: Requirements 5.1, 5.4**

### Property 12: Intent Parameter Extraction

*For any* text classified as SET_BRIGHTNESS containing a numeric value, the parser SHALL extract an integer brightness between 0 and 100. For any text classified as PLAY_MUSIC mentioning a music type, the parser SHALL extract the music_type string. For any text classified as CHANGE_LIGHT_MODE mentioning a mode, the parser SHALL extract the mode string.

**Validates: Requirements 5.5, 5.7, 5.8**

### Property 13: Hardware Intent Bypasses LLM

*For any* hardware command intent (TURN_ON_LIGHT, TURN_OFF_LIGHT, INCREASE_BRIGHTNESS, DECREASE_BRIGHTNESS, SET_BRIGHTNESS, CHANGE_LIGHT_MODE, PLAY_MUSIC, STOP_MUSIC), the Voice_Pipeline SHALL NOT call the LLM_Service for response generation, and SHALL route directly to the Command_Dispatcher.

**Validates: Requirements 6.3**

### Property 14: Text Input Skips STT

*For any* text input received via the process-text endpoint, the Voice_Pipeline SHALL NOT invoke the STT_Service, and SHALL begin processing from intent parsing with the provided text.

**Validates: Requirements 6.2**

### Property 15: Conversation Context Window

*For any* CHAT intent within a session that has N previous conversation turns, the LLM_Service SHALL receive min(N, 10) most recent turns as context. The context SHALL never exceed 10 turns.

**Validates: Requirements 6.4, 9.4**

### Property 16: Information Response Summarization

*For any* external information response that exceeds 3 sentences, the final output sent to TTS SHALL be summarized to 3 sentences or fewer. Responses of 3 sentences or fewer SHALL pass through without modification.

**Validates: Requirements 6.5, 12.5**

### Property 17: Pipeline Failure Produces Fallback

*For any* stage of the Voice_Pipeline that fails (STT, intent parsing, LLM, TTS, external info), the system SHALL return a safe fallback response in the configured language and SHALL NOT crash or leave the session in an inconsistent state.

**Validates: Requirements 6.6, 17.1, 17.2, 17.3**

### Property 18: Command Structure Completeness

*For any* hardware intent resolved by the Voice_Pipeline, the Command_Dispatcher SHALL produce a command containing all required fields: messageType="COMMAND", a non-empty commandId, the correct deviceId, the command type matching the intent, a payload dict, and an ISO 8601 timestamp.

**Validates: Requirements 7.1**

### Property 19: Offline Device Command Failure

*For any* command targeting a device with status OFFLINE, the Command_Dispatcher SHALL mark the command as FAILED with reason "device_offline" without attempting WebSocket delivery.

**Validates: Requirements 7.3**

### Property 20: Brightness Adjustment Clamping

*For any* current brightness value B (0 ≤ B ≤ 100), INCREASE_BRIGHTNESS SHALL produce min(B + 20, 100) and DECREASE_BRIGHTNESS SHALL produce max(B - 20, 0). The result SHALL always remain within [0, 100].

**Validates: Requirements 10.3, 10.4**

### Property 21: Music Track Selection

*For any* PLAY_MUSIC intent with a music type that exists in the catalog, the selected track SHALL match the requested type. If a duration is specified, the command payload SHALL include durationSeconds matching the requested value.

**Validates: Requirements 11.1, 11.2**

### Property 22: Device ID Format Validation

*For any* string S, the device_id validation SHALL accept S if and only if S matches the MAC address format (XX:XX:XX:XX:XX:XX where X is a hexadecimal digit). All other formats SHALL be rejected.

**Validates: Requirements 16.5**

### Property 23: Configuration Loading from Environment

*For any* set of environment variables containing all required keys (OPENAI_API_KEY, DATABASE_URL, DEVICE_AUTH_TOKEN), the Pydantic Settings object SHALL be populated with the correct values. Missing required keys SHALL raise a validation error at startup.

**Validates: Requirements 16.1, 16.2**

### Property 24: Robustness Against Malformed Input

*For any* malformed WebSocket input (invalid JSON, unexpected binary data, unknown message types, missing required fields), the Backend_Server SHALL NOT crash, SHALL NOT close the connection (unless protocol requires it), and SHALL log the error with appropriate context.

**Validates: Requirements 17.5, 3.8, 3.9**

### Property 25: Disconnection Cleanup

*For any* session in any state when the device disconnects unexpectedly, all pending commands for that device SHALL be marked as FAILED, session resources SHALL be cleaned up, and the disconnection SHALL be logged with session context.

**Validates: Requirements 17.4**

### Property 26: Command Persistence and Retrieval

*For any* command created and dispatched, it SHALL be retrievable from PostgreSQL by command_id with the correct type, device_id, payload, and current status.

**Validates: Requirements 7.6**

### Property 27: Conversation Record Completeness

*For any* completed voice interaction, the stored conversation record SHALL contain non-null device_id, session_id, user_text, intent, and timestamp. The ai_response field SHALL be non-null for CHAT and information intents.

**Validates: Requirements 9.1**

### Property 28: No Secrets in Logs

*For any* log entry produced during any operation, the log output SHALL NOT contain raw API key values or authentication token values. References to secrets SHALL use masked or key-name-only format.

**Validates: Requirements 9.5**

---

## Error Handling

### Error Categories and Responses

| Category | Trigger | Response | Recovery |
|----------|---------|----------|----------|
| Auth Failure | Invalid/missing token | Reject WebSocket (401) | Device must reconnect with valid token |
| Hello Timeout | No hello within 10s | Close WebSocket | Device must reconnect |
| STT Failure | Whisper API error | Fallback: "Mình chưa nghe rõ..." | Log, continue session |
| LLM Timeout | GPT-4o-mini > 5s | Fallback: safe response | Log, retry once for transient |
| TTS Failure | TTS-1 API error | Return text-only response | Log, session continues |
| Device Offline | Command to offline device | Mark FAILED, reason: device_offline | Log, notify caller |
| Command Timeout | No ACK within 5s | Mark TIMED_OUT | Log, background task checks |
| Invalid Brightness | Value outside 0-100 | Validation error response | Reject command |
| Malformed JSON | Unparseable text frame | Discard, log | Session unaffected |
| Unknown Message Type | Unrecognized type field | Discard, log | Session unaffected |
| DB Unreachable | Connection failure | Startup: fail fast. Runtime: retry with backoff | Alert in logs |
| Opus Decode Error | Invalid binary frame | Discard frame, log | Continue buffering |
| External API Failure | Weather/info provider down | Fallback: "Dịch vụ tạm thời không khả dụng" | Log, retry once |

### Error Response Schema

```python
class ErrorResponse(BaseModel):
    error: str           # machine-readable error code
    message: str         # human-readable description
    details: dict = {}   # additional context
    timestamp: str       # ISO 8601
```

### Graceful Shutdown Sequence

1. Stop accepting new WebSocket connections
2. Send close frame to all active WebSocket sessions
3. Wait up to 5 seconds for in-flight operations to complete
4. Mark all pending commands as FAILED with reason "server_shutdown"
5. Flush pending database writes
6. Close database connection pool
7. Exit

---

## Testing Strategy

### Testing Approach

The testing strategy uses a dual approach:

1. **Property-based tests** (using `hypothesis` library) — verify universal properties across randomized inputs with minimum 100 iterations per property
2. **Example-based unit tests** (using `pytest`) — verify specific scenarios, edge cases, and integration points

### Why Property-Based Testing Applies

This backend has significant pure logic suitable for PBT:
- Intent parsing (text → intent classification with parameter extraction)
- Brightness clamping arithmetic
- Command construction from intents
- State validation logic
- Header validation
- Message format verification
- Device ID format validation

### Property-Based Testing Configuration

- **Library**: `hypothesis` (Python)
- **Minimum iterations**: 100 per property
- **Tag format**: `# Feature: lamp-cham-ai-backend, Property {N}: {title}`

### Test Organization

```
backend/tests/
  unit/
    test_intent_parser.py          # Properties 11, 12 + examples
    test_command_builder.py        # Properties 18, 19, 20, 21
    test_device_state.py           # Properties 7, 8, 9, 10
    test_brightness_logic.py       # Property 20
    test_header_validation.py      # Property 1
    test_device_id_validation.py   # Property 22
    test_message_format.py         # Properties 2, 5, 6
    test_config_loading.py         # Property 23
    test_voice_pipeline.py         # Properties 13, 14, 15, 16, 17
    test_conversation_context.py   # Property 15
    test_secrets_logging.py        # Property 28
  integration/
    test_websocket_session.py      # Properties 3, 4, 24, 25
    test_full_pipeline.py          # End-to-end voice flow
    test_db_persistence.py         # Properties 7, 26, 27
    test_fake_device_flow.py       # Simulator integration
  scenarios/
    test_turn_on_light.py
    test_set_brightness.py
    test_reject_invalid_brightness.py
    test_weather_query.py
    test_chat_conversation.py
    test_play_music.py
    test_device_offline.py
```

### Example-Based Tests (Key Scenarios)

| Scenario | What's Tested |
|----------|---------------|
| Hello timeout | Device doesn't send hello → connection closed after 10s |
| Command timeout | Device doesn't ACK → command marked TIMED_OUT after 5s |
| Heartbeat offline | No heartbeat for 90s → device marked OFFLINE |
| STT failure fallback | Whisper fails → Vietnamese fallback message returned |
| LLM timeout fallback | GPT-4o-mini times out → safe fallback response |
| Graceful shutdown | SIGTERM → all connections closed, DB flushed |
| Music type not found | Unknown type → default track selected |
| Interactive text mode | Text via process-text → STT skipped, pipeline runs |

### Mock Strategy

All AI providers have mock implementations for testing:
- `MockSTTService`: Returns predefined transcriptions
- `MockLLMService`: Returns predefined responses, tracks calls
- `MockTTSService`: Returns silent Opus frames
- `MockExternalInfoService`: Returns canned weather/time data

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Linux Server                               │
│              i7-12700F / 32GB RAM / RTX 4090                 │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  systemd services                                        │ │
│  │                                                           │ │
│  │  ┌──────────────────┐  ┌──────────────────────────────┐ │ │
│  │  │  lampai-backend   │  │  cloudflared                  │ │ │
│  │  │  (uvicorn)        │  │  (tunnel to Cloudflare)       │ │ │
│  │  │  port: 8000       │  │  maps domain → localhost:8000 │ │ │
│  │  └──────────────────┘  └──────────────────────────────┘ │ │
│  │                                                           │ │
│  │  ┌──────────────────┐                                    │ │
│  │  │  postgresql       │                                    │ │
│  │  │  port: 5432       │                                    │ │
│  │  └──────────────────┘                                    │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  Environment: .env file (not in git)                          │
│  Logs: structured JSON to stdout + journald                   │
│  Process manager: systemd (auto-restart on failure)           │
└─────────────────────────────────────────────────────────────┘
         │
         │ Cloudflare Tunnel (encrypted)
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Cloudflare Edge                                             │
│  domain.example.com → tunnel → localhost:8000                │
│  WSS termination, DDoS protection                            │
└─────────────────────────────────────────────────────────────┘
         │
         │ WSS (port 443)
         ▼
┌─────────────────────────────────────────────────────────────┐
│  ESP32 Devices / Fake Device Simulator                       │
│  Connect via wss://domain.example.com/ws                     │
└─────────────────────────────────────────────────────────────┘
```

### Deployment Configuration

**Cloudflare Tunnel config** (`~/.cloudflared/config.yml`):
```yaml
tunnel: <tunnel-id>
credentials-file: /home/user/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: lampai.example.com
    service: http://localhost:8000
  - service: http_status:404
```

**Uvicorn startup**:
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1 --ws websockets
```

Note: Single worker because WebSocket sessions are stateful and stored in-memory. For scaling, use a shared session store (Redis) in the future.

### Required Environment Variables

```env
# Required
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/lampai
DEVICE_AUTH_TOKEN=<shared-secret-for-device-auth>

# Optional
LANGUAGE=vi                    # vi or en, default: vi
LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
SERVER_PORT=8000
HELLO_TIMEOUT_SECONDS=10
COMMAND_TIMEOUT_SECONDS=5
HEARTBEAT_TIMEOUT_SECONDS=90
MAX_AUDIO_BUFFER_SECONDS=60
MAX_CONVERSATION_CONTEXT=10
WEATHER_API_KEY=               # for weather provider
TIMEZONE=Asia/Ho_Chi_Minh
```

---

## Web Admin Dashboard Architecture

### Overview

The Web Admin Dashboard is a React/Next.js application providing administrative control over devices, voice configurations, system instructions, music catalog, and conversation history. It communicates with the FastAPI backend via REST API endpoints and WebSocket for real-time updates.

### Deployment Strategy

The admin dashboard is built as a Next.js static export and served by FastAPI's `StaticFiles` middleware at the `/admin` path. This avoids running a separate Node.js server in production.

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                            │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │  /ws          │  │  /api/*      │  │  /admin (StaticFiles) │ │
│  │  WebSocket    │  │  REST API    │  │  React SPA            │ │
│  └──────────────┘  └──────────────┘  └───────────────────────┘ │
│                           │                                       │
│                           ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  /api/admin/*  (Admin API Routes)                         │   │
│  │  - POST /api/admin/login                                  │   │
│  │  - GET  /api/admin/dashboard                              │   │
│  │  - WebSocket /ws/admin (real-time device state push)      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Authentication Flow

```mermaid
sequenceDiagram
    participant Browser as Admin Browser
    participant API as FastAPI Backend
    participant DB as PostgreSQL

    Browser->>API: POST /api/admin/login {username, password}
    API->>DB: SELECT admin_users WHERE username = ?
    DB-->>API: {id, username, password_hash}
    API->>API: bcrypt.verify(password, password_hash)
    alt Valid credentials
        API->>API: Generate JWT (exp: 24h)
        API-->>Browser: 200 {token, expires_at}
        Browser->>Browser: Store token in localStorage
    else Invalid credentials
        API-->>Browser: 401 {error: "invalid_credentials"}
    end

    Note over Browser,API: Subsequent requests
    Browser->>API: GET /api/admin/devices (Authorization: Bearer <token>)
    API->>API: Verify JWT signature + expiry
    alt Token valid
        API-->>Browser: 200 {devices: [...]}
    else Token expired/invalid
        API-->>Browser: 401 {error: "token_expired"}
    end
```

### Authentication Design Decisions

| Decision | Rationale |
|----------|-----------|
| Simple username/password (no OAuth) | Self-hosted system, max 2 admins, no external IdP needed |
| bcrypt for password hashing | Industry standard, resistant to brute force |
| JWT session tokens (24h expiry) | Stateless verification, no server-side session store needed |
| Max 2 admin accounts | Single-user/small-team deployment, simplifies management |

### Frontend Component Structure

```
admin-frontend/
  src/
    app/
      layout.tsx              # Root layout with auth provider
      page.tsx                # Dashboard overview
      login/page.tsx          # Login form
      devices/
        page.tsx              # Device list
        [deviceId]/page.tsx   # Per-device config
      voice-config/page.tsx   # Global voice configuration
      instructions/page.tsx   # System instructions editor
      music/page.tsx          # Music catalog management
      conversations/page.tsx  # Conversation history viewer
      test/page.tsx           # Test environment
    components/
      AuthProvider.tsx        # JWT token management
      DeviceCard.tsx          # Device status card
      LampVisualizer.tsx      # Visual lamp state representation
      AudioPlayer.tsx         # Music preview player
      ConversationTable.tsx   # Paginated conversation list
    hooks/
      useWebSocket.ts         # Admin WebSocket connection
      useAuth.ts              # Authentication state
    lib/
      api.ts                  # REST API client
      types.ts                # TypeScript interfaces
```

### Real-Time Communication

The admin dashboard maintains a WebSocket connection to `/ws/admin` for receiving real-time updates:

- Device state changes (online/offline, brightness, mode changes)
- New conversation entries
- Command status updates (SENT → SUCCESS/FAILED/TIMED_OUT)

```python
# Admin WebSocket message types
class AdminWSMessage(BaseModel):
    type: Literal["device_state", "conversation", "command_status"]
    payload: dict
    timestamp: str
```

---

## Voice Configuration Design

### Database Schema

```sql
CREATE TABLE voice_configurations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id       VARCHAR(17) REFERENCES devices(device_id),  -- NULL = global config
    voice           VARCHAR(20) NOT NULL DEFAULT 'nova',         -- alloy, echo, fable, onyx, nova, shimmer
    speed           NUMERIC(3,2) NOT NULL DEFAULT 1.0 CHECK (speed >= 0.25 AND speed <= 4.0),
    stt_language    VARCHAR(5) NOT NULL DEFAULT 'vi',            -- vi, en, auto
    tts_language    VARCHAR(5) NOT NULL DEFAULT 'vi',            -- vi, en
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(device_id)  -- one config per device, NULL device_id = global
);

-- Ensure only one global config (device_id IS NULL)
CREATE UNIQUE INDEX idx_voice_config_global ON voice_configurations ((device_id IS NULL)) WHERE device_id IS NULL;
```

### Configuration Resolution Logic

```python
class VoiceConfigService:
    async def get_effective_config(self, device_id: str) -> VoiceConfig:
        """Resolve effective voice config: per-device overrides global."""
        device_config = await self.repo.get_by_device(device_id)
        if device_config:
            return device_config
        global_config = await self.repo.get_global()
        if global_config:
            return global_config
        return VoiceConfig.defaults()  # hardcoded fallback

    async def update_config(self, device_id: str | None, config: VoiceConfigUpdate) -> VoiceConfig:
        """Update config. device_id=None for global."""
        validated = self._validate(config)
        return await self.repo.upsert(device_id, validated)
```

### Config Propagation to Active Sessions

When a voice configuration is updated:
1. The config is persisted to the database
2. An event is emitted to the admin WebSocket (`type: "config_updated"`)
3. The next voice session for the affected device(s) reads the new config from DB
4. Active sessions are NOT interrupted — changes apply to subsequent sessions only

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/voice-config` | Get global voice config |
| PUT | `/api/admin/voice-config` | Update global voice config |
| GET | `/api/admin/devices/{device_id}/voice-config` | Get per-device voice config |
| PUT | `/api/admin/devices/{device_id}/voice-config` | Set per-device voice config |
| DELETE | `/api/admin/devices/{device_id}/voice-config` | Remove per-device override (fall back to global) |

### Pydantic Schemas

```python
class VoiceConfigUpdate(BaseModel):
    voice: Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"] | None = None
    speed: float = Field(None, ge=0.25, le=4.0)
    stt_language: Literal["vi", "en", "auto"] | None = None
    tts_language: Literal["vi", "en"] | None = None

class VoiceConfigResponse(BaseModel):
    id: str
    device_id: str | None
    voice: str
    speed: float
    stt_language: str
    tts_language: str
    updated_at: datetime
    is_global: bool
```

---

## System Instructions Design

### Database Schema

```sql
CREATE TABLE system_instructions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id       VARCHAR(17) REFERENCES devices(device_id),  -- NULL = global
    content         TEXT NOT NULL,
    template_name   VARCHAR(50),  -- NULL if custom, otherwise template identifier
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    UNIQUE(device_id, version)
);

CREATE INDEX idx_system_instructions_device_active ON system_instructions(device_id, is_active);
CREATE INDEX idx_system_instructions_device_version ON system_instructions(device_id, version DESC);
```

### Version History Mechanism

When system instructions are updated:
1. The current active version is marked `is_active = false`
2. A new row is inserted with `version = previous_version + 1` and `is_active = true`
3. All previous versions remain in the database for history viewing

```python
class SystemInstructionsService:
    async def get_active(self, device_id: str | None) -> SystemInstructions | None:
        """Get active instructions for device (or global if device_id is None)."""
        return await self.repo.get_active_by_device(device_id)

    async def get_effective(self, device_id: str) -> str:
        """Resolve effective instructions: per-device overrides global."""
        device_instructions = await self.get_active(device_id)
        if device_instructions:
            return device_instructions.content
        global_instructions = await self.get_active(None)
        if global_instructions:
            return global_instructions.content
        return self.DEFAULT_INSTRUCTIONS

    async def update(self, device_id: str | None, content: str, template_name: str | None = None) -> SystemInstructions:
        """Save new version, deactivate previous."""
        current = await self.get_active(device_id)
        new_version = (current.version + 1) if current else 1
        if current:
            await self.repo.deactivate(current.id)
        return await self.repo.create(device_id, content, template_name, new_version)

    async def get_history(self, device_id: str | None) -> list[SystemInstructions]:
        """Get all versions for a device (or global), ordered by version DESC."""
        return await self.repo.get_all_versions(device_id)
```

### Template System

Pre-built templates are stored as constants in the codebase:

```python
SYSTEM_INSTRUCTION_TEMPLATES = {
    "bedtime_companion": """Bạn là một người bạn đồng hành lúc đi ngủ. Hãy nói nhẹ nhàng, 
    ấm áp, và giúp người dùng thư giãn. Gợi ý các bài tập thở, kể chuyện ngắn, 
    hoặc phát nhạc ru khi được yêu cầu.""",
    
    "study_buddy": """Bạn là một trợ lý học tập thông minh. Hãy giúp người dùng tập trung, 
    nhắc nhở giờ nghỉ, và trả lời các câu hỏi kiến thức một cách ngắn gọn, dễ hiểu.""",
    
    "meditation_guide": """Bạn là một hướng dẫn viên thiền định. Hãy nói chậm rãi, 
    bình tĩnh, và hướng dẫn người dùng qua các bài tập chánh niệm và thở.""",
    
    "general_assistant": """Bạn là trợ lý AI của đèn LunaLamp. Hãy trả lời ngắn gọn, 
    thân thiện, và hữu ích. Bạn có thể điều khiển đèn, phát nhạc, và trả lời câu hỏi.""",
}
```

### Injection into LLM Calls

```python
# In VoicePipeline, when routing to LLM:
async def _handle_chat(self, session: Session, user_text: str) -> str:
    system_instructions = await self.instructions_service.get_effective(session.device_id)
    context = await self.conversation_repo.get_recent(session.session_id, limit=10)
    
    messages = [
        {"role": "system", "content": system_instructions},
        *[{"role": turn.role, "content": turn.content} for turn in context],
        {"role": "user", "content": user_text},
    ]
    return await self.llm_service.generate(messages)
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/instructions` | Get active global instructions |
| POST | `/api/admin/instructions` | Save new global instructions |
| GET | `/api/admin/instructions/history` | Get global version history |
| GET | `/api/admin/instructions/templates` | List available templates |
| GET | `/api/admin/devices/{device_id}/instructions` | Get per-device instructions |
| POST | `/api/admin/devices/{device_id}/instructions` | Save per-device instructions |
| GET | `/api/admin/devices/{device_id}/instructions/history` | Per-device version history |

---

## Music Catalog Management Design

### File Upload Storage Strategy

Audio files are stored on the local filesystem at a configurable path (`UPLOAD_DIR` environment variable, default: `./uploads/music/`).

```
uploads/
  music/
    <uuid>_<original_filename>.mp3
    <uuid>_<original_filename>.ogg
    ...
```

File naming uses UUID prefix to avoid collisions while preserving the original filename for readability.

### Audio File Validation

```python
SUPPORTED_AUDIO_FORMATS = {"mp3", "ogg", "wav", "flac"}
SUPPORTED_CONTENT_TYPES = {
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
}
MAX_UPLOAD_SIZE_MB = 50

async def validate_audio_upload(file: UploadFile) -> str:
    """Validate uploaded file. Returns file extension or raises ValidationError."""
    if file.content_type not in SUPPORTED_CONTENT_TYPES:
        raise ValidationError(f"Unsupported format: {file.content_type}")
    
    # Check file size
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"File exceeds {MAX_UPLOAD_SIZE_MB}MB limit")
    
    await file.seek(0)
    return SUPPORTED_CONTENT_TYPES[file.content_type]
```

### Updated Music Catalog Schema

```sql
-- Extended music_catalog table (adds file storage fields)
ALTER TABLE music_catalog ADD COLUMN file_path TEXT;           -- local file path (for uploads)
ALTER TABLE music_catalog ADD COLUMN file_size_bytes INTEGER;  -- file size
ALTER TABLE music_catalog ADD COLUMN content_type VARCHAR(30); -- MIME type
ALTER TABLE music_catalog ALTER COLUMN source_url DROP NOT NULL; -- URL optional if file uploaded

-- Track source: either source_url (external) OR file_path (uploaded), at least one required
ALTER TABLE music_catalog ADD CONSTRAINT chk_music_source 
    CHECK (source_url IS NOT NULL OR file_path IS NOT NULL);
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/music` | List all tracks in catalog |
| POST | `/api/admin/music` | Add track (URL-based) |
| POST | `/api/admin/music/upload` | Upload audio file + create track |
| PUT | `/api/admin/music/{track_id}` | Update track metadata |
| DELETE | `/api/admin/music/{track_id}` | Delete track + file |
| GET | `/api/admin/music/{track_id}/stream` | Stream audio for browser preview |
| PUT | `/api/admin/music/{track_id}/default` | Set as default track |

### Browser Preview Mechanism

The `/api/admin/music/{track_id}/stream` endpoint serves the audio file with appropriate headers for browser playback:

```python
@router.get("/api/admin/music/{track_id}/stream")
async def stream_track(track_id: str, auth: AdminAuth = Depends()):
    track = await music_service.get_track(track_id)
    if track.file_path:
        return FileResponse(track.file_path, media_type=track.content_type)
    elif track.source_url:
        return RedirectResponse(track.source_url)
```

---

## Conversation History Design

### Query Patterns

```python
class ConversationQueryParams(BaseModel):
    device_id: str | None = None
    session_id: str | None = None
    search: str | None = None          # text search in user_text and ai_response
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    order: Literal["asc", "desc"] = "desc"
```

### Search Implementation

Text search uses PostgreSQL `ILIKE` for simple substring matching:

```sql
SELECT * FROM conversations
WHERE (user_text ILIKE '%search_term%' OR ai_response ILIKE '%search_term%')
  AND (device_id = :device_id OR :device_id IS NULL)
  AND (created_at >= :date_from OR :date_from IS NULL)
  AND (created_at <= :date_to OR :date_to IS NULL)
ORDER BY created_at DESC
LIMIT :page_size OFFSET (:page - 1) * :page_size;
```

### Pagination Strategy

- Default page size: 50 entries
- Maximum page size: 200 entries
- Response includes pagination metadata:

```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
```

### Export Format Specifications

**JSON Export:**
```json
{
  "exported_at": "2025-01-15T10:00:00Z",
  "filters": {"device_id": "AA:BB:CC:DD:EE:FF", "date_from": "...", "date_to": "..."},
  "total_records": 150,
  "conversations": [
    {
      "id": "uuid",
      "device_id": "AA:BB:CC:DD:EE:FF",
      "session_id": "session_abc",
      "user_text": "bật đèn lên",
      "ai_response": "Đã bật đèn",
      "intent": "TURN_ON_LIGHT",
      "latency_ms": 450,
      "stage_latencies": {"stt": 120, "intent": 15, "tts": 200},
      "created_at": "2025-01-15T09:30:00Z"
    }
  ]
}
```

**CSV Export:**
```
id,device_id,session_id,user_text,ai_response,intent,latency_ms,stt_ms,intent_ms,llm_ms,tts_ms,created_at
uuid,AA:BB:CC:DD:EE:FF,session_abc,bật đèn lên,Đã bật đèn,TURN_ON_LIGHT,450,120,15,,200,2025-01-15T09:30:00Z
```

### Bulk Delete Mechanism

```python
async def bulk_delete(self, date_from: datetime, date_to: datetime, device_id: str | None = None) -> int:
    """Delete conversations within date range. Returns count of deleted records."""
    query = delete(Conversation).where(
        Conversation.created_at >= date_from,
        Conversation.created_at <= date_to,
    )
    if device_id:
        query = query.where(Conversation.device_id == device_id)
    result = await self.session.execute(query)
    await self.session.commit()
    return result.rowcount
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/conversations` | List conversations (paginated, filterable) |
| GET | `/api/admin/conversations/export` | Export as JSON or CSV |
| DELETE | `/api/admin/conversations` | Bulk delete by date range |
| DELETE | `/api/admin/conversations/{id}` | Delete single conversation |

---

## Web-Based Test Environment Design

### Overview

The Test Environment at `/test` provides a browser-based interface that simulates the full lamp experience. It registers as a virtual device with a dedicated `device_id` and communicates with the backend through the same voice pipeline as real devices.

### Virtual Device Registration

```python
TEST_DEVICE_ID = "TE:ST:00:00:00:01"  # Reserved test device MAC

class TestEnvironmentService:
    async def initialize(self) -> str:
        """Register test device if not exists, return session_id."""
        device = await self.device_service.get_or_create(TEST_DEVICE_ID)
        session = await self.session_manager.create_session(
            device_id=TEST_DEVICE_ID,
            hello_msg=HelloMessage(
                type="hello", version=1, transport="websocket",
                audio_params=AudioParams(format="opus", sample_rate=16000, channels=1, frame_duration=60)
            )
        )
        return session.session_id
```

### Browser Audio Capture → WebSocket → STT Flow

```mermaid
sequenceDiagram
    participant Browser as Test Browser
    participant WS as WebSocket /ws/test
    participant VP as Voice Pipeline
    participant STT as STT Service
    participant TTS as TTS Service

    Browser->>Browser: navigator.mediaDevices.getUserMedia()
    Browser->>Browser: MediaRecorder (opus/webm)
    Browser->>WS: Binary audio chunks (opus frames)
    WS->>VP: buffer_audio(frames)
    Browser->>WS: JSON {type: "listen", state: "stop"}
    WS->>VP: finalize_audio()
    VP->>STT: transcribe(audio_buffer)
    STT-->>VP: "bật đèn lên"
    VP-->>WS: JSON {type: "stt", text: "bật đèn lên"}
    WS-->>Browser: Display transcription
    VP->>VP: Intent parsing + routing
    VP-->>WS: JSON {type: "pipeline_stage", stage: "intent", data: {...}}
    WS-->>Browser: Display intent result
    VP->>TTS: synthesize("Đã bật đèn")
    TTS-->>VP: opus frames
    VP-->>WS: Binary TTS audio
    WS-->>Browser: Play audio via Web Audio API
```

### Real-Time State Visualization

The test environment maintains a WebSocket connection that receives push updates for:

- **Pipeline stages**: Each stage (STT, intent, routing, LLM, TTS) pushes its result as it completes
- **Device state**: Lamp visualization updates when commands are processed
- **Command status**: Shows command dispatch and ACK status

```python
class TestWSMessage(BaseModel):
    type: Literal["pipeline_stage", "device_state", "command_status", "tts_audio"]
    stage: str | None = None  # stt, intent, routing, llm, tts
    data: dict
    timestamp: str
```

### Component Architecture

```
/test page components:
├── TextInput          # Type messages for text-based pipeline
├── MicrophoneButton   # Browser audio capture
├── PipelineViewer     # Real-time stage-by-stage results
│   ├── STTResult      # Transcription display
│   ├── IntentResult   # Intent + params display
│   ├── CommandResult  # Command JSON display
│   └── ResponseText   # AI response text
├── AudioPlayer        # TTS playback
└── LampVisualizer     # Visual lamp state
    ├── PowerIndicator
    ├── BrightnessSlider (read-only)
    ├── ColorDisplay
    └── ModeLabel
```

---

## Device Configuration Management Design

### Configuration Hierarchy

```
┌─────────────────────────────────────────────┐
│           Configuration Resolution           │
│                                              │
│  1. Per-device config (if exists)            │
│     ↓ (fallback if not set)                  │
│  2. Global config (if exists)                │
│     ↓ (fallback if not set)                  │
│  3. Hardcoded defaults                       │
└─────────────────────────────────────────────┘
```

This hierarchy applies independently to:
- Voice configuration (voice, speed, stt_language, tts_language)
- System instructions (content, template)
- Volume level

```python
class DeviceConfigService:
    async def get_effective_config(self, device_id: str) -> EffectiveDeviceConfig:
        """Resolve all config layers for a device."""
        voice_config = await self.voice_config_service.get_effective_config(device_id)
        instructions = await self.instructions_service.get_effective(device_id)
        device_state = await self.device_service.get_state(device_id)
        
        return EffectiveDeviceConfig(
            device_id=device_id,
            voice=voice_config,
            system_instructions=instructions,
            volume=device_state.volume,
        )
```

### Real-Time State Push via WebSocket

The admin dashboard connects to `/ws/admin` and receives device state updates:

```python
class AdminWebSocketManager:
    """Manages WebSocket connections from admin dashboard clients."""
    
    async def broadcast_device_state(self, device_id: str, state: DeviceState):
        """Push device state update to all connected admin clients."""
        message = AdminWSMessage(
            type="device_state",
            payload={"device_id": device_id, **state.model_dump()},
            timestamp=datetime.utcnow().isoformat()
        )
        for ws in self.admin_connections:
            await ws.send_json(message.model_dump())

    async def broadcast_command_status(self, command_id: str, status: str):
        """Push command status update to admin clients."""
        message = AdminWSMessage(
            type="command_status",
            payload={"command_id": command_id, "status": status},
            timestamp=datetime.utcnow().isoformat()
        )
        for ws in self.admin_connections:
            await ws.send_json(message.model_dump())
```

### Command Sending from Web UI

Administrators can send test commands to devices from the dashboard:

```python
@router.post("/api/admin/devices/{device_id}/commands")
async def send_admin_command(
    device_id: str,
    command: AdminCommandRequest,
    auth: AdminAuth = Depends(),
):
    device = await device_service.get_state(device_id)
    if device.status == DeviceStatus.OFFLINE:
        raise HTTPException(status_code=409, detail="Device is offline")
    
    result = await command_dispatcher.dispatch(
        device_id=device_id,
        intent=ParsedIntent(intent=command.type, params=command.payload, source="admin")
    )
    return {"command_id": result.command_id, "status": result.status}
```

---

## Updated Database Schema (Requirements 19-25)

### New Tables

```sql
-- Admin user accounts (max 2)
CREATE TABLE admin_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(50) NOT NULL UNIQUE,
    password_hash   VARCHAR(128) NOT NULL,  -- bcrypt hash
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Voice configurations (global + per-device)
CREATE TABLE voice_configurations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id       VARCHAR(17) REFERENCES devices(device_id),
    voice           VARCHAR(20) NOT NULL DEFAULT 'nova',
    speed           NUMERIC(3,2) NOT NULL DEFAULT 1.0 CHECK (speed >= 0.25 AND speed <= 4.0),
    stt_language    VARCHAR(5) NOT NULL DEFAULT 'vi',
    tts_language    VARCHAR(5) NOT NULL DEFAULT 'vi',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(device_id)
);
CREATE UNIQUE INDEX idx_voice_config_global 
    ON voice_configurations ((device_id IS NULL)) WHERE device_id IS NULL;

-- System instructions with version history
CREATE TABLE system_instructions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id       VARCHAR(17) REFERENCES devices(device_id),
    content         TEXT NOT NULL,
    template_name   VARCHAR(50),
    version         INTEGER NOT NULL DEFAULT 1,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(device_id, version)
);
CREATE INDEX idx_system_instructions_device_active 
    ON system_instructions(device_id, is_active);

-- Uploaded files tracking
CREATE TABLE uploaded_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        VARCHAR(255) NOT NULL,
    path            TEXT NOT NULL,
    content_type    VARCHAR(50) NOT NULL,
    size_bytes      INTEGER NOT NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Music Catalog Extensions

```sql
-- Add upload-related columns to music_catalog
ALTER TABLE music_catalog ADD COLUMN file_path TEXT;
ALTER TABLE music_catalog ADD COLUMN file_size_bytes INTEGER;
ALTER TABLE music_catalog ADD COLUMN content_type VARCHAR(30);
ALTER TABLE music_catalog ALTER COLUMN source_url DROP NOT NULL;
ALTER TABLE music_catalog ADD CONSTRAINT chk_music_source 
    CHECK (source_url IS NOT NULL OR file_path IS NOT NULL);
```

---

## Updated API Endpoints (Requirements 19-25)

### Admin Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/login` | Authenticate admin, return JWT |
| GET | `/api/admin/dashboard` | Dashboard overview (device count, connections, recent conversations) |

### Device Management (Admin)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/devices` | List all devices with status |
| GET | `/api/admin/devices/{device_id}` | Get device details + state |
| GET | `/api/admin/devices/{device_id}/config` | Get effective device config |
| PUT | `/api/admin/devices/{device_id}/config` | Update per-device config |
| POST | `/api/admin/devices/{device_id}/commands` | Send test command to device |
| GET | `/api/admin/devices/{device_id}/commands` | Get command history for device |

### Voice Configuration (Admin)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/voice-config` | Get global voice config |
| PUT | `/api/admin/voice-config` | Update global voice config |
| GET | `/api/admin/devices/{device_id}/voice-config` | Get per-device voice config |
| PUT | `/api/admin/devices/{device_id}/voice-config` | Set per-device voice config |
| DELETE | `/api/admin/devices/{device_id}/voice-config` | Remove per-device override |

### System Instructions (Admin)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/instructions` | Get active global instructions |
| POST | `/api/admin/instructions` | Save new global instructions |
| GET | `/api/admin/instructions/history` | Get global version history |
| GET | `/api/admin/instructions/templates` | List available templates |
| GET | `/api/admin/devices/{device_id}/instructions` | Get per-device instructions |
| POST | `/api/admin/devices/{device_id}/instructions` | Save per-device instructions |
| GET | `/api/admin/devices/{device_id}/instructions/history` | Per-device version history |

### Music Catalog (Admin)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/music` | List all tracks |
| POST | `/api/admin/music` | Add track (URL-based) |
| POST | `/api/admin/music/upload` | Upload audio file + create track |
| PUT | `/api/admin/music/{track_id}` | Update track metadata |
| DELETE | `/api/admin/music/{track_id}` | Delete track + associated file |
| GET | `/api/admin/music/{track_id}/stream` | Stream audio for preview |
| PUT | `/api/admin/music/{track_id}/default` | Set as default track |

### Conversations (Admin)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/conversations` | List conversations (paginated, filterable) |
| GET | `/api/admin/conversations/export` | Export as JSON or CSV |
| DELETE | `/api/admin/conversations` | Bulk delete by date range |
| DELETE | `/api/admin/conversations/{id}` | Delete single conversation |

### WebSocket Endpoints (Admin)

| Path | Description |
|------|-------------|
| `/ws/admin` | Real-time admin updates (device state, commands, conversations) |
| `/ws/test` | Test environment WebSocket (pipeline stages, TTS audio) |

---

## Updated Correctness Properties (Requirements 19-25)

### Property 29: Admin Authentication Validation

*For any* password string P and stored bcrypt hash H, authentication SHALL succeed if and only if P is the original password used to generate H. Storing any password SHALL produce a hash that is not equal to the plaintext password.

**Validates: Requirements 19.3, 19.6**

### Property 30: JWT Token Lifecycle

*For any* valid admin login, the issued JWT token SHALL have an expiry exactly 24 hours from issuance. For any token past its expiry time, authentication SHALL be rejected. For any token before its expiry time with a valid signature, authentication SHALL succeed.

**Validates: Requirements 19.7**

### Property 31: Speech Speed Validation

*For any* numeric value V, the speech speed validation SHALL accept V if and only if 0.25 ≤ V ≤ 4.0. Values outside this range SHALL be rejected with a validation error.

**Validates: Requirements 20.2, 20.7**

### Property 32: Configuration Hierarchy Override

*For any* device with a per-device configuration (voice config or system instructions) and any global configuration, the effective configuration for that device SHALL equal the per-device values. For any device without a per-device configuration, the effective configuration SHALL equal the global values.

**Validates: Requirements 20.6, 21.5**

### Property 33: Configuration Propagation

*For any* valid voice configuration or system instructions update, all subsequent voice sessions for the affected device(s) SHALL use the new configuration values. The previous configuration SHALL NOT be used after the update is persisted.

**Validates: Requirements 20.5, 25.6**

### Property 34: System Instructions Injection

*For any* configured system instructions text and any user message processed through the CHAT intent path, the LLM_Service call SHALL include the system instructions as the system message. The system message content SHALL exactly match the active instructions for the device.

**Validates: Requirements 21.4**

### Property 35: System Instructions Version History

*For any* sequence of N system instruction updates for a device (or global), the version history SHALL contain exactly N entries ordered by version number descending, each with the correct content and timestamp. No previous version SHALL be lost.

**Validates: Requirements 21.6**

### Property 36: Audio File Format Validation

*For any* uploaded file, the validation SHALL accept it if and only if its content type maps to one of the supported formats (mp3, ogg, wav, flac). Files with unsupported content types SHALL be rejected with a validation error.

**Validates: Requirements 22.7**

### Property 37: Conversation Search Filtering

*For any* search term and set of conversation records, the search results SHALL contain only records where the user_text or ai_response contains the search term (case-insensitive). No record matching the search term SHALL be excluded from results.

**Validates: Requirements 23.2**

### Property 38: Conversation Ordering

*For any* set of conversation records returned by the list endpoint, the records SHALL be ordered by created_at timestamp descending. For any two adjacent records in the result, the first record's timestamp SHALL be greater than or equal to the second's.

**Validates: Requirements 23.1**

### Property 39: Bulk Delete by Date Range

*For any* date range [from, to] and set of conversation records, bulk delete SHALL remove exactly those records with created_at within the range (inclusive). Records outside the range SHALL remain unaffected.

**Validates: Requirements 23.5**

### Property 40: Conversation Export Completeness

*For any* export request with filter criteria, the exported data SHALL contain exactly the records matching the filter (device_id, date range). Each exported record SHALL include all required fields: id, device_id, session_id, user_text, ai_response, intent, latency_ms, stage_latencies, and created_at.

**Validates: Requirements 23.6, 23.3**

### Property 41: Conversation Pagination

*For any* conversation dataset of size N and page size S (default 50), requesting page P SHALL return at most S entries. The total_pages SHALL equal ceil(N/S). The union of all pages SHALL equal the complete dataset with no duplicates or omissions.

**Validates: Requirements 23.7**

---

## Updated Error Handling (Requirements 19-25)

### Additional Error Categories

| Category | Trigger | Response | Recovery |
|----------|---------|----------|----------|
| Admin Auth Failure | Invalid username/password | 401 {error: "invalid_credentials"} | Retry with correct credentials |
| Token Expired | JWT past 24h expiry | 401 {error: "token_expired"} | Re-login |
| Max Admins Reached | Attempt to create 3rd admin | 409 {error: "max_admins_reached"} | Delete existing admin first |
| Invalid Speed | Speed outside 0.25-4.0 | 422 {error: "validation_error"} | Correct input value |
| Unsupported Audio Format | Upload non-mp3/ogg/wav/flac | 422 {error: "unsupported_format"} | Upload supported format |
| File Too Large | Upload exceeds 50MB | 413 {error: "file_too_large"} | Reduce file size |
| Device Offline (Admin Cmd) | Send command to offline device | 409 {error: "device_offline"} | Wait for device to reconnect |
| Export Too Large | Export request > 10000 records | 413 {error: "export_too_large"} | Narrow date range filter |

---

## Updated Testing Strategy (Requirements 19-25)

### Additional Test Files

```
backend/tests/
  unit/
    test_admin_auth.py              # Properties 29, 30
    test_voice_config_validation.py # Property 31
    test_config_hierarchy.py        # Properties 32, 33
    test_system_instructions.py     # Properties 34, 35
    test_audio_upload_validation.py # Property 36
    test_conversation_queries.py    # Properties 37, 38, 39, 40, 41
  integration/
    test_admin_login_flow.py        # Full login → JWT → protected endpoint
    test_voice_config_propagation.py # Config change → session uses new config
    test_music_upload_flow.py       # Upload → validate → store → stream
    test_conversation_export.py     # Query → export JSON/CSV
    test_admin_websocket.py         # Real-time state push to admin
    test_test_environment.py        # Virtual device registration + pipeline
```

### Property-Based Test Examples (New)

```python
# test_admin_auth.py
# Feature: lamp-cham-ai-backend, Property 29: Admin Authentication Validation
@given(password=st.text(min_size=1, max_size=72))
def test_bcrypt_hash_never_equals_plaintext(password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    assert hashed != password.encode()
    assert bcrypt.checkpw(password.encode(), hashed)

# test_voice_config_validation.py
# Feature: lamp-cham-ai-backend, Property 31: Speech Speed Validation
@given(speed=st.floats(min_value=-100, max_value=100))
def test_speech_speed_validation(speed):
    if 0.25 <= speed <= 4.0:
        assert validate_speed(speed) is True
    else:
        with pytest.raises(ValidationError):
            validate_speed(speed)

# test_conversation_queries.py
# Feature: lamp-cham-ai-backend, Property 38: Conversation Ordering
@given(conversations=st.lists(st.builds(Conversation, created_at=st.datetimes()), min_size=2))
def test_conversations_ordered_descending(conversations):
    result = sort_conversations_desc(conversations)
    for i in range(len(result) - 1):
        assert result[i].created_at >= result[i + 1].created_at
```

### Additional Environment Variables

```env
# Admin Dashboard
ADMIN_JWT_SECRET=<random-secret-for-jwt-signing>
ADMIN_JWT_EXPIRY_HOURS=24

# File Upload
UPLOAD_DIR=./uploads/music
MAX_UPLOAD_SIZE_MB=50
```
