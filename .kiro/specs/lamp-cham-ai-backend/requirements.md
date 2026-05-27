# Requirements Document

## Introduction

This document specifies the requirements for the Lamp Chạm AI Backend — a Python/FastAPI WebSocket server that implements the XiaoZhi ESP32 communication protocol. The backend serves as the central AI orchestration layer for the LunaLamp smart bedside lamp, handling voice processing, intent parsing, device command dispatch, and state management. It integrates with OpenAI providers (Whisper STT, GPT-4o-mini LLM, TTS-1) via LangChain, stores data in PostgreSQL, and is exposed publicly through Cloudflare Tunnel.

## Glossary

- **Backend_Server**: The Python/FastAPI WebSocket server that orchestrates AI services, manages device state, and dispatches commands to connected devices.
- **Device**: An ESP32-based smart lamp (or Fake_Device_Simulator) that connects to the Backend_Server via WebSocket.
- **Fake_Device_Simulator**: A Python-based software simulator that emulates ESP32 device behavior for development and testing without physical hardware.
- **XiaoZhi_Protocol**: The WebSocket communication protocol used between the Device and Backend_Server, consisting of a JSON hello handshake, binary Opus audio streaming, and JSON message dispatch.
- **Intent_Parser**: The service component that classifies user input text into one of the canonical intent types.
- **Voice_Pipeline**: The end-to-end processing chain from audio/text input through STT, intent parsing, routing, response generation, TTS, and command dispatch.
- **Command_Dispatcher**: The service that builds structured JSON commands and sends them to connected devices via WebSocket.
- **Device_State**: The canonical representation of a device's current status including power, brightness, mode, volume, and connectivity.
- **Session**: A single WebSocket connection lifecycle from hello handshake through audio exchange to disconnection, identified by a session_id.
- **STT_Service**: The speech-to-text service abstraction (OpenAI Whisper implementation).
- **LLM_Service**: The large language model service abstraction (OpenAI GPT-4o-mini implementation).
- **TTS_Service**: The text-to-speech service abstraction (OpenAI TTS-1 implementation).
- **Opus_Codec**: The audio codec used for bidirectional audio streaming between Device and Backend_Server.
- **Heartbeat**: A periodic signal sent by the Device to indicate it is online and reachable.
- **MCP_Message**: Model Context Protocol message used for IoT control, following JSON-RPC 2.0 format within the XiaoZhi protocol.
- **Cloudflare_Tunnel**: The secure tunnel service that exposes the locally-hosted Backend_Server to the public internet.
- **Web_Admin_Dashboard**: A React/Next.js web application served at the /admin path that provides administrative control over devices, configurations, and conversation history.
- **Test_Environment**: A web-based interface served at the /test path that simulates the lamp experience for development and testing without physical hardware.
- **System_Instructions**: Custom system prompt text configured by administrators that defines the AI personality and behavior for LLM conversations.
- **Voice_Configuration**: Per-device or global settings controlling TTS voice selection, speech speed, and STT/TTS language preferences.
- **Music_Catalog**: The collection of audio tracks stored in the system, manageable through the Web_Admin_Dashboard, used for ambient music playback.
- **Conversation_History**: The stored record of all voice interactions including user text, AI responses, intent classifications, and timing metadata.
- **Device_Configuration**: Per-device settings including voice, language, system instructions, and volume that override global defaults.

## Requirements

### Requirement 1: WebSocket Protocol Handshake

**User Story:** As a Device, I want to establish a WebSocket connection with the Backend_Server using the XiaoZhi protocol handshake, so that I can begin an audio communication session.

#### Acceptance Criteria

1. WHEN a Device connects via WebSocket with headers Authorization (Bearer token format), Protocol-Version (integer), Device-Id (MAC address string), and Client-Id (UUID string), THE Backend_Server SHALL validate that all four headers are present and non-empty, that Authorization contains a recognized token, and accept the connection by completing the WebSocket upgrade.
2. IF a Device connects with a missing, empty, or unrecognized Authorization header, THEN THE Backend_Server SHALL reject the WebSocket upgrade and not complete the connection.
3. WHEN a Device sends a hello message containing type "hello", version (integer matching Protocol-Version header), transport "websocket", and audio_params (with format, sample_rate, channels, and frame_duration fields), THE Backend_Server SHALL respond with a JSON hello message containing type "hello", transport "websocket", a server-generated session_id string, and server audio_params (format, sample_rate, channels, frame_duration) within 2 seconds.
4. IF a Device fails to send a valid hello message within 10 seconds of connection, THEN THE Backend_Server SHALL close the WebSocket connection with a close frame.
5. IF a Device sends a hello message with an unsupported protocol version, THEN THE Backend_Server SHALL send a JSON error message indicating the supported version numbers (1, 2, 3) and then close the WebSocket connection.
6. THE Backend_Server SHALL support binary protocol version 1 (raw Opus frames with no additional header) as the default audio framing format.

### Requirement 2: Binary Audio Streaming

**User Story:** As a Device, I want to stream Opus-encoded audio to the Backend_Server and receive Opus-encoded audio responses, so that voice interaction works in real-time.

#### Acceptance Criteria

1. WHEN the Backend_Server receives binary WebSocket frames from a Device during an active session in listening state, THE Backend_Server SHALL decode the frames as Opus audio at the sample rate specified in the Device's hello handshake audio_params (16kHz mono, 60ms frame duration).
2. WHEN the Backend_Server needs to send TTS audio to a Device, THE Backend_Server SHALL encode the audio as Opus frames at 24kHz mono with 60ms frame duration and send them as binary WebSocket frames.
3. WHILE a Device is in listening state, THE Backend_Server SHALL buffer incoming audio frames until the Device sends a listen message with state "stop", or until the buffer reaches a maximum duration of 60 seconds, whichever occurs first.
4. THE Backend_Server SHALL handle Opus encoding and decoding on the server side without requiring the Device to change audio format.
5. IF the Backend_Server receives a binary WebSocket frame that fails Opus decoding, THEN THE Backend_Server SHALL discard the frame, log the decoding error with session_id and frame sequence context, and continue processing subsequent frames without closing the connection.
6. IF the Backend_Server receives binary WebSocket frames while the session is not in listening state, THEN THE Backend_Server SHALL discard the frames without processing.
7. IF the audio buffer reaches the maximum duration of 60 seconds, THEN THE Backend_Server SHALL stop buffering, submit the accumulated audio to the STT_Service for processing, and send a listen message with state "stop" to the Device.

### Requirement 3: JSON Message Dispatch

**User Story:** As a Device, I want to send and receive JSON messages with type-based routing, so that the Backend_Server can coordinate STT results, LLM responses, TTS state, and control commands.

#### Acceptance Criteria

1. WHEN the Backend_Server receives a JSON message with type "listen", state "start", and a mode field value of "auto", "manual", or "realtime", THE Backend_Server SHALL transition the session to listening state and begin accepting audio frames for STT processing using the specified mode.
2. WHEN the Backend_Server receives a JSON message with type "listen" and state "stop", THE Backend_Server SHALL finalize the buffered audio and submit it to the STT_Service within 500 milliseconds of message receipt.
3. WHEN the Backend_Server receives a JSON message with type "abort", THE Backend_Server SHALL cancel any in-progress STT processing, LLM generation, and TTS playback for that session, and transition the session to idle state.
4. WHEN the Backend_Server completes STT processing, THE Backend_Server SHALL send a JSON message with type "stt", the session_id, and a "text" field containing the transcribed text (maximum 4096 characters) to the Device.
5. WHEN the Backend_Server begins streaming TTS audio, THE Backend_Server SHALL send a JSON message with type "tts" and state "start" before the first audio frame, and SHALL send a JSON message with type "tts", state "sentence_start", and a "text" field containing the current sentence before each sentence's audio begins.
6. WHEN the Backend_Server finishes streaming TTS audio, THE Backend_Server SHALL send a JSON message with type "tts" and state "stop" after the last audio frame has been sent.
7. WHEN the Backend_Server receives a JSON message with type "mcp" containing a payload that conforms to JSON-RPC 2.0 structure, THE Backend_Server SHALL route the payload to the MCP handler for IoT command processing.
8. IF the Backend_Server receives a WebSocket text frame that is not valid JSON, THEN THE Backend_Server SHALL log the malformed frame and discard it without closing the connection or affecting other sessions.
9. IF the Backend_Server receives a valid JSON message with a missing or unrecognized type field, THEN THE Backend_Server SHALL log the message type and session_id and discard the message without affecting the session state.
10. WHEN the Backend_Server receives a JSON message with type "listen" and state "detect", THE Backend_Server SHALL acknowledge the wake word detection event and prepare the session for subsequent listen "start" or audio streaming.

### Requirement 4: Device Registration and State Management

**User Story:** As a Developer, I want devices to register with the Backend_Server and maintain their state, so that the system can track connected devices and their current configuration.

#### Acceptance Criteria

1. WHEN a Device sends a registration request with a device_id, THE Backend_Server SHALL create a device record in PostgreSQL with initial state values and return a success confirmation.
2. WHEN a Device sends a heartbeat message, THE Backend_Server SHALL update the lastSeenAt timestamp and confirm the device status as ONLINE.
3. IF a Device fails to send a heartbeat within 90 seconds of the last heartbeat, THEN THE Backend_Server SHALL mark the device status as OFFLINE.
4. THE Backend_Server SHALL persist device state including deviceId, status, lightPower, brightness, color, mode, volume, isPlayingMusic, and lastSeenAt in PostgreSQL.
5. WHEN a Device sends a COMMAND_ACK with updated state fields, THE Backend_Server SHALL update the stored device state to match the acknowledged values.
6. THE Backend_Server SHALL validate that brightness values are integers between 0 and 100 inclusive before persisting state changes.

### Requirement 5: Intent Parsing

**User Story:** As a Backend_Server, I want to classify user input into canonical intent types, so that I can route requests to the appropriate handler without unnecessary LLM calls.

#### Acceptance Criteria

1. WHEN user text matches a deterministic pattern for hardware commands (light on/off, brightness, mode, music play/stop), THE Intent_Parser SHALL return the matching intent and any extracted parameters without calling the LLM_Service.
2. WHEN user text does not match any deterministic pattern, THE Intent_Parser SHALL use the LLM_Service to classify the text into one of the canonical intent types within 5 seconds.
3. THE Intent_Parser SHALL support these canonical intent types: TURN_ON_LIGHT, TURN_OFF_LIGHT, INCREASE_BRIGHTNESS, DECREASE_BRIGHTNESS, SET_BRIGHTNESS, CHANGE_LIGHT_MODE, PLAY_MUSIC, STOP_MUSIC, ASK_WEATHER, ASK_TIME, ASK_GENERAL_INFO, CHAT, UNKNOWN.
4. THE Intent_Parser SHALL match deterministic patterns in both Vietnamese and English, with Vietnamese patterns evaluated first when both languages could match.
5. WHEN the Intent_Parser classifies text as SET_BRIGHTNESS, THE Intent_Parser SHALL extract the target brightness value as an integer between 0 and 100 from the text and include it in the parsed result.
6. IF the LLM_Service is unavailable during intent parsing, THEN THE Intent_Parser SHALL return intent type UNKNOWN and log the failure.
7. WHEN the Intent_Parser classifies text as PLAY_MUSIC, THE Intent_Parser SHALL extract the music type (e.g., sleep, rain, nature) from the text and include it in the parsed result.
8. WHEN the Intent_Parser classifies text as CHANGE_LIGHT_MODE, THE Intent_Parser SHALL extract the requested mode from the text and include it in the parsed result.
9. IF the Intent_Parser cannot extract a valid brightness value from a SET_BRIGHTNESS classified text, THEN THE Intent_Parser SHALL return intent type UNKNOWN and include an error indication in the parsed result.

### Requirement 6: Voice Pipeline Processing

**User Story:** As a User, I want to speak to the lamp and receive an appropriate voice response or action, so that I can interact naturally with the device.

#### Acceptance Criteria

1. WHEN audio input is received from a Device, THE Voice_Pipeline SHALL process it through STT, intent parsing, routing, response generation, and TTS in sequence.
2. WHEN text input is received via the process-text API endpoint, THE Voice_Pipeline SHALL skip STT and begin processing from intent parsing.
3. WHILE processing a hardware command intent (TURN_ON_LIGHT, TURN_OFF_LIGHT, INCREASE_BRIGHTNESS, DECREASE_BRIGHTNESS, SET_BRIGHTNESS, CHANGE_LIGHT_MODE, PLAY_MUSIC, STOP_MUSIC), THE Voice_Pipeline SHALL bypass the LLM_Service, route directly to the Command_Dispatcher, and send a short voice confirmation to the Device via TTS_Service indicating the action taken.
4. WHILE processing a CHAT intent, THE Voice_Pipeline SHALL send the user text and up to 10 most recent conversation turns as context to the LLM_Service and convert the response to speech via TTS_Service.
5. WHILE processing an information intent (ASK_WEATHER, ASK_TIME, ASK_GENERAL_INFO), THE Voice_Pipeline SHALL query the mapped external tool (weather provider for ASK_WEATHER, system clock for ASK_TIME, LLM_Service for ASK_GENERAL_INFO), summarize the result via LLM_Service if the raw response exceeds 3 sentences, and convert the final result to speech.
6. IF any stage of the Voice_Pipeline fails, THEN THE Voice_Pipeline SHALL return a safe fallback response in the configured language and log the error with the failed stage name and latency metadata.
7. WHEN the Voice_Pipeline completes processing a request, THE Voice_Pipeline SHALL log the latency in milliseconds for each stage (STT, intent parsing, routing, response generation, TTS) as a structured log entry.

### Requirement 7: Command Dispatch and Acknowledgement

**User Story:** As a Backend_Server, I want to send structured commands to devices and track their execution status, so that lamp behavior is controlled reliably.

#### Acceptance Criteria

1. WHEN the Voice_Pipeline resolves a hardware intent, THE Command_Dispatcher SHALL build a structured JSON command with messageType, commandId, deviceId, type, payload, and timestamp fields.
2. WHEN a command is built, THE Command_Dispatcher SHALL send it to the target Device via the active WebSocket connection.
3. IF the target Device is offline when a command is dispatched, THEN THE Command_Dispatcher SHALL mark the command as FAILED with reason "device_offline" and log the failure.
4. WHEN a Device sends a COMMAND_ACK message, THE Backend_Server SHALL update the command status to SUCCESS or FAILED based on the ack status field.
5. IF a Device does not acknowledge a command within 5 seconds, THEN THE Backend_Server SHALL mark the command as TIMED_OUT.
6. THE Backend_Server SHALL store all commands and their statuses in PostgreSQL for audit and debugging.

### Requirement 8: AI Provider Integration via LangChain

**User Story:** As a Developer, I want AI provider calls orchestrated through LangChain with proper abstraction, so that providers can be swapped or mocked without changing business logic.

#### Acceptance Criteria

1. THE Backend_Server SHALL use LangChain to orchestrate calls to the LLM_Service (OpenAI GPT-4o-mini).
2. THE STT_Service SHALL use OpenAI Whisper API to transcribe audio, accepting Opus-encoded input and returning text.
3. THE TTS_Service SHALL use OpenAI TTS-1 API to convert text to audio, returning Opus-encoded output suitable for streaming.
4. THE Backend_Server SHALL implement each AI provider behind an abstract interface (STT_Service, LLM_Service, TTS_Service) to allow mock implementations for testing.
5. THE Backend_Server SHALL load all AI provider API keys from environment variables and never hard-code them in source code.
6. IF an AI provider call fails, THEN THE Backend_Server SHALL retry once for transient errors and return a structured error response for persistent failures.

### Requirement 9: Conversation History and Logging

**User Story:** As a Developer, I want conversation history and structured logs stored in PostgreSQL, so that I can debug interactions and maintain conversation context.

#### Acceptance Criteria

1. WHEN a voice interaction completes, THE Backend_Server SHALL store a conversation record containing device_id, session_id, user_text, ai_response, intent, latency_ms, and timestamp in PostgreSQL.
2. THE Backend_Server SHALL use structured logging with fields: event_name, device_id, session_id, command_id, intent, latency_ms, status, and error_code for every state transition.
3. WHEN a command is created, sent, acknowledged, or fails, THE Backend_Server SHALL log each transition as a separate structured log entry.
4. THE Backend_Server SHALL maintain conversation context per session to enable multi-turn dialogue within a single WebSocket session.
5. THE Backend_Server SHALL never log raw API keys or authentication tokens in any log output.

### Requirement 10: Smart Light Control

**User Story:** As a User, I want to control the lamp by voice (turn on/off, set brightness, change mode), so that I can adjust lighting without physical interaction.

#### Acceptance Criteria

1. WHEN the Intent_Parser identifies a TURN_ON_LIGHT intent, THE Command_Dispatcher SHALL send a TURN_ON_LIGHT command to the Device.
2. WHEN the Intent_Parser identifies a SET_BRIGHTNESS intent with a value, THE Command_Dispatcher SHALL validate the brightness is between 0 and 100 and send a SET_BRIGHTNESS command with the validated value.
3. WHEN the Intent_Parser identifies an INCREASE_BRIGHTNESS intent, THE Command_Dispatcher SHALL increase the current brightness by 20 (clamped to 100) and send a SET_BRIGHTNESS command.
4. WHEN the Intent_Parser identifies a DECREASE_BRIGHTNESS intent, THE Command_Dispatcher SHALL decrease the current brightness by 20 (clamped to 0) and send a SET_BRIGHTNESS command.
5. IF a SET_BRIGHTNESS command specifies a value outside 0-100, THEN THE Backend_Server SHALL reject the command with a validation error response.
6. WHEN the Intent_Parser identifies a CHANGE_LIGHT_MODE intent, THE Command_Dispatcher SHALL send a CHANGE_LIGHT_MODE command with the requested mode in the payload.

### Requirement 11: Music Playback Control

**User Story:** As a User, I want to play or stop relaxing sounds through the lamp by voice, so that I can enjoy ambient audio for sleep or relaxation.

#### Acceptance Criteria

1. WHEN the Intent_Parser identifies a PLAY_MUSIC intent, THE Backend_Server SHALL select a track from the music catalog matching the requested type and send a PLAY_MUSIC command to the Device.
2. WHEN the Intent_Parser identifies a PLAY_MUSIC intent with a duration, THE Backend_Server SHALL include durationSeconds in the command payload.
3. WHEN the Intent_Parser identifies a STOP_MUSIC intent, THE Command_Dispatcher SHALL send a STOP_MUSIC command to the Device.
4. THE Backend_Server SHALL maintain a static music catalog in PostgreSQL containing track id, title, type, source URL, and duration for each available track.
5. IF the requested music type has no matching track in the catalog, THEN THE Backend_Server SHALL select a default relaxing track and log the fallback.

### Requirement 12: External Information Services

**User Story:** As a User, I want to ask factual questions (weather, time, general knowledge) and receive a concise voice answer, so that the lamp serves as a helpful information assistant.

#### Acceptance Criteria

1. WHEN the Intent_Parser identifies an ASK_WEATHER intent, THE Backend_Server SHALL query the weather provider and return a summarized voice response.
2. WHEN the Intent_Parser identifies an ASK_TIME intent, THE Backend_Server SHALL return the current time in the configured timezone as a voice response.
3. WHEN the Intent_Parser identifies an ASK_GENERAL_INFO intent, THE Backend_Server SHALL use the LLM_Service to generate a concise answer suitable for TTS output.
4. IF an external information provider is unavailable, THEN THE Backend_Server SHALL return a transparent fallback message indicating the service is temporarily unavailable.
5. THE Backend_Server SHALL summarize external information responses to be concise enough for comfortable TTS playback (under 3 sentences for simple queries).

### Requirement 13: Fake Device Simulator

**User Story:** As a Developer, I want a software simulator that emulates ESP32 device behavior, so that I can develop and test all backend features without physical hardware.

#### Acceptance Criteria

1. THE Fake_Device_Simulator SHALL connect to the Backend_Server via WebSocket with Authorization, Protocol-Version, Device-Id, and Client-Id headers, send a hello message with type, version, transport, and audio_params fields, and consider the handshake complete upon receiving a server hello response containing a session_id.
2. THE Fake_Device_Simulator SHALL send periodic heartbeat messages every 30 seconds while connected.
3. WHEN the Fake_Device_Simulator receives a command message (TURN_ON_LIGHT, TURN_OFF_LIGHT, SET_BRIGHTNESS, CHANGE_LIGHT_MODE, PLAY_MUSIC, STOP_MUSIC, PLAY_TTS_RESPONSE), THE Fake_Device_Simulator SHALL update its internal state (lightPower, brightness, color, mode, volume, isPlayingMusic) accordingly and send a COMMAND_ACK response within 1 second.
4. THE Fake_Device_Simulator SHALL simulate audio input by sending Opus-encoded frames at 16kHz mono with 60ms frame duration to the Backend_Server, triggered by an explicit user command or scenario script.
5. THE Fake_Device_Simulator SHALL support configurable failure modes (offline, timeout, command_failed, invalid_payload, and audio_playback_failed) activated via command-line argument --failure-mode or runtime interactive command during execution.
6. THE Fake_Device_Simulator SHALL be runnable as a standalone Python script with command-line arguments for --device-id, --backend-url, and optional --failure-mode.
7. THE Fake_Device_Simulator SHALL log all received commands and state transitions using structured logging with fields: event_name, device_id, session_id, command_id, timestamp, and state_snapshot.
8. THE Fake_Device_Simulator SHALL support an interactive mode where the developer can type text input that is sent to the Backend_Server as if the user spoke, using the listen start/stop and text message flow of the XiaoZhi protocol.

### Requirement 14: Database Persistence

**User Story:** As a Developer, I want all device state, commands, and conversation history stored in PostgreSQL, so that data survives server restarts and supports debugging.

#### Acceptance Criteria

1. THE Backend_Server SHALL use PostgreSQL 16 as the primary data store for device records, command logs, conversation history, and music catalog.
2. WHEN the Backend_Server starts, THE Backend_Server SHALL verify database connectivity and run any pending schema migrations.
3. THE Backend_Server SHALL use async database access to avoid blocking the event loop during database operations.
4. IF the database is unreachable at startup, THEN THE Backend_Server SHALL fail with a clear error message indicating the connection problem.
5. THE Backend_Server SHALL store database connection credentials in environment variables, not in source code or configuration files committed to version control.

### Requirement 15: Cloudflare Tunnel Exposure

**User Story:** As a Developer, I want the Backend_Server accessible from the public internet via Cloudflare Tunnel, so that real ESP32 devices can connect from any network.

#### Acceptance Criteria

1. THE Backend_Server SHALL be configurable to run behind a Cloudflare Tunnel that maps the configured domain to the local WebSocket port.
2. THE Backend_Server SHALL support WebSocket upgrade requests when accessed through the Cloudflare Tunnel.
3. THE Backend_Server SHALL include documentation for configuring the Cloudflare Tunnel with the correct protocol (http or websocket) for the backend service.

### Requirement 16: Configuration and Security

**User Story:** As a Developer, I want all secrets and configuration managed through environment variables with a settings object, so that the system is secure and portable across environments.

#### Acceptance Criteria

1. THE Backend_Server SHALL load all configuration from environment variables via a Pydantic Settings object.
2. THE Backend_Server SHALL require these environment variables: OPENAI_API_KEY, DATABASE_URL, and DEVICE_AUTH_TOKEN.
3. THE Backend_Server SHALL provide a .env.example file documenting all required and optional environment variables.
4. WHEN a Device connects with an invalid or missing Authorization header, THE Backend_Server SHALL reject the WebSocket connection with a 401 status.
5. THE Backend_Server SHALL validate device_id format and reject requests with malformed identifiers.
6. THE Backend_Server SHALL configure language preference (Vietnamese or English) via an environment variable with Vietnamese as the default.

### Requirement 17: Error Handling and Resilience

**User Story:** As a Backend_Server, I want to handle all expected failure cases gracefully, so that the system remains stable and provides useful feedback even when components fail.

#### Acceptance Criteria

1. IF the STT_Service fails to transcribe audio, THEN THE Backend_Server SHALL respond with a fallback message "Mình chưa nghe rõ, bạn nói lại được không?" (or English equivalent based on configuration).
2. IF the LLM_Service times out, THEN THE Backend_Server SHALL return a safe fallback response and log the timeout with latency metadata.
3. IF the TTS_Service fails, THEN THE Backend_Server SHALL return the text response without audio and include error metadata in the response.
4. IF a Device disconnects unexpectedly during a session, THEN THE Backend_Server SHALL clean up session resources, mark pending commands as FAILED, and log the disconnection.
5. THE Backend_Server SHALL never crash due to malformed input from a Device, invalid JSON, or unexpected WebSocket frame types.
6. THE Backend_Server SHALL implement graceful shutdown that closes all active WebSocket connections and flushes pending database writes.

### Requirement 18: Health and Observability

**User Story:** As a Developer, I want health check endpoints and observable metrics, so that I can monitor the Backend_Server status and diagnose issues quickly.

#### Acceptance Criteria

1. THE Backend_Server SHALL expose a GET /api/health endpoint that returns server status, database connectivity, and active WebSocket connection count.
2. THE Backend_Server SHALL include request latency in structured log entries for all voice pipeline operations.
3. WHEN the Backend_Server starts successfully, THE Backend_Server SHALL log a startup event with the configured port, database status, and tunnel availability.

### Requirement 19: Web Admin Dashboard

**User Story:** As an Administrator, I want a web-based admin dashboard accessible at the /admin path, so that I can monitor device status, manage configurations, and view system activity from any browser.

#### Acceptance Criteria

1. THE Web_Admin_Dashboard SHALL be built with React and Next.js and served at the /admin path of the same domain as the Backend_Server.
2. WHEN an Administrator navigates to the /admin path, THE Web_Admin_Dashboard SHALL require authentication via username and password before granting access.
3. THE Web_Admin_Dashboard SHALL support a maximum of 2 administrator accounts with credentials stored securely (hashed) in the database.
4. WHEN an Administrator logs in successfully, THE Web_Admin_Dashboard SHALL display a dashboard overview showing: count of online devices, count of active WebSocket connections, and a list of the 10 most recent conversations.
5. THE Web_Admin_Dashboard SHALL render responsively for both desktop (minimum 1024px width) and mobile (minimum 320px width) viewports.
6. IF an Administrator provides incorrect credentials, THEN THE Web_Admin_Dashboard SHALL display an error message and not grant access.
7. WHEN an Administrator is authenticated, THE Web_Admin_Dashboard SHALL issue a session token valid for 24 hours and require re-authentication after expiry.

### Requirement 20: Voice Configuration Management

**User Story:** As an Administrator, I want to configure TTS voice, speech speed, and language settings through the Web Admin Dashboard, so that I can customize the lamp's voice behavior without modifying code.

#### Acceptance Criteria

1. THE Web_Admin_Dashboard SHALL provide a voice configuration interface allowing selection of TTS voice from the options: alloy, echo, fable, onyx, nova, shimmer.
2. THE Web_Admin_Dashboard SHALL provide a speech speed configuration control accepting values from 0.25 to 4.0 inclusive.
3. THE Web_Admin_Dashboard SHALL provide an STT language configuration with options: Vietnamese (vi), English (en), or auto-detect (auto).
4. THE Web_Admin_Dashboard SHALL provide a TTS language configuration independent from the STT language setting, with options: Vietnamese (vi) and English (en).
5. WHEN an Administrator saves a Voice_Configuration change, THE Backend_Server SHALL apply the new settings to all subsequent voice sessions without requiring a server restart.
6. THE Web_Admin_Dashboard SHALL support per-device Voice_Configuration that overrides the global configuration for a specific device.
7. IF an Administrator sets speech speed outside the range 0.25 to 4.0, THEN THE Web_Admin_Dashboard SHALL reject the input with a validation error message.

### Requirement 21: System Instructions and AI Personality Configuration

**User Story:** As an Administrator, I want to write custom system prompts and select pre-built AI personality templates through the Web Admin Dashboard, so that I can control how the AI responds to users.

#### Acceptance Criteria

1. THE Web_Admin_Dashboard SHALL provide a text input area for writing custom System_Instructions that define the AI personality and behavior.
2. THE Web_Admin_Dashboard SHALL offer pre-built System_Instructions templates: "Bedtime companion", "Study buddy", "Meditation guide", and "General assistant".
3. WHEN an Administrator selects a pre-built template, THE Web_Admin_Dashboard SHALL populate the text input area with the template content, allowing further editing before saving.
4. WHEN a conversation with a Device begins, THE Backend_Server SHALL include the configured System_Instructions as the system message in every LLM_Service call for that session.
5. THE Web_Admin_Dashboard SHALL support per-device System_Instructions that override the global System_Instructions for a specific device.
6. WHEN an Administrator saves System_Instructions, THE Backend_Server SHALL store the previous version and maintain a version history of instruction changes with timestamps.
7. THE Web_Admin_Dashboard SHALL display the version history of System_Instructions changes and allow viewing previous versions.

### Requirement 22: Music Catalog Management

**User Story:** As an Administrator, I want to manage the music catalog through the Web Admin Dashboard (add, edit, delete tracks, upload files), so that I can maintain the available ambient audio library.

#### Acceptance Criteria

1. THE Web_Admin_Dashboard SHALL provide an interface to add new tracks to the Music_Catalog by specifying an external URL as the audio source.
2. THE Web_Admin_Dashboard SHALL provide an interface to upload audio files directly to the Backend_Server for storage.
3. THE Web_Admin_Dashboard SHALL provide an interface to edit track metadata including: title, type (RAIN, SLEEP, NATURE, OCEAN, MEDITATION), and duration in seconds.
4. WHEN an Administrator deletes a track from the Music_Catalog, THE Backend_Server SHALL remove the track record from the database and delete any locally stored audio file associated with the track.
5. THE Web_Admin_Dashboard SHALL provide an interface to designate one track as the default track, and THE Backend_Server SHALL use this track when no specific type matches a music request.
6. THE Web_Admin_Dashboard SHALL provide an audio player to preview and play tracks directly in the browser.
7. IF an Administrator uploads an audio file, THEN THE Backend_Server SHALL validate that the file is a supported audio format (mp3, ogg, wav, flac) and reject unsupported formats with an error message.

### Requirement 23: Conversation History Viewer

**User Story:** As an Administrator, I want to view, search, and manage conversation history through the Web Admin Dashboard, so that I can monitor interactions and debug issues.

#### Acceptance Criteria

1. THE Web_Admin_Dashboard SHALL display all conversations grouped by device_id and session_id, ordered by timestamp descending.
2. THE Web_Admin_Dashboard SHALL provide a text search function that filters conversations by matching against user_text and ai_response content.
3. THE Web_Admin_Dashboard SHALL display for each conversation entry: user_text, ai_response, intent classification, total latency_ms, stage_latencies breakdown, and timestamp.
4. WHEN an Administrator selects individual conversations for deletion, THE Backend_Server SHALL remove the selected records from the database.
5. THE Web_Admin_Dashboard SHALL provide a bulk delete function that removes all conversations within a specified date range.
6. THE Web_Admin_Dashboard SHALL provide an export function that downloads conversations as JSON or CSV format, filtered by device and date range.
7. THE Web_Admin_Dashboard SHALL paginate conversation results with a default of 50 entries per page.

### Requirement 24: Web-Based Test Environment

**User Story:** As a Developer, I want a web-based test interface that simulates the lamp experience, so that I can test the full voice pipeline and device commands without physical hardware or the fake_device.py simulator.

#### Acceptance Criteria

1. THE Test_Environment SHALL be accessible at the /test path of the same domain as the Backend_Server.
2. THE Test_Environment SHALL provide a text input field for typing messages that are processed through the Voice_Pipeline as if spoken by a user.
3. THE Test_Environment SHALL provide a microphone button that captures browser audio, sends it to the Backend_Server for STT processing, and displays the transcription result.
4. WHEN the Voice_Pipeline processes a request from the Test_Environment, THE Test_Environment SHALL display in real-time: the STT transcription result, the parsed intent and parameters, the command sent to the device (if applicable), and the AI text response.
5. WHEN the Backend_Server returns a TTS audio response, THE Test_Environment SHALL play the audio in the browser.
6. THE Test_Environment SHALL display a visual representation of the simulated lamp state including: power (on/off), brightness level, current color, and current mode, updated in real-time as commands are processed.
7. THE Test_Environment SHALL register itself as a virtual device with the Backend_Server using a dedicated test device_id, enabling full command dispatch and state tracking.

### Requirement 25: Device Configuration Management

**User Story:** As an Administrator, I want to view all registered devices and manage per-device settings through the Web Admin Dashboard, so that I can configure and monitor each lamp individually.

#### Acceptance Criteria

1. THE Web_Admin_Dashboard SHALL display a list of all registered devices showing: device_id, status (ONLINE/OFFLINE), last_seen_at timestamp, and current mode.
2. THE Web_Admin_Dashboard SHALL provide a per-device configuration interface for: Voice_Configuration (voice, speed, language), System_Instructions, and volume level.
3. WHILE a Device is connected, THE Web_Admin_Dashboard SHALL display the device state in real-time including: lightPower, brightness, color, mode, volume, and isPlayingMusic.
4. THE Web_Admin_Dashboard SHALL provide a command interface to send test commands (TURN_ON_LIGHT, TURN_OFF_LIGHT, SET_BRIGHTNESS, CHANGE_LIGHT_MODE, PLAY_MUSIC, STOP_MUSIC) to a selected device and display the command result.
5. THE Web_Admin_Dashboard SHALL display a command history for each device showing: command type, payload, status (PENDING, SENT, SUCCESS, FAILED, TIMED_OUT), and timestamps.
6. WHEN an Administrator updates per-device configuration, THE Backend_Server SHALL apply the new settings immediately for subsequent interactions with that device.
7. IF a Device is offline when an Administrator sends a test command, THEN THE Web_Admin_Dashboard SHALL display a message indicating the device is offline and the command cannot be delivered.
