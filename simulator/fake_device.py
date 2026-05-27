#!/usr/bin/env python3
"""Fake Device Simulator for Lamp Chạm backend testing.

Usage:
    python simulator/fake_device.py --device-id AA:BB:CC:DD:EE:FF --backend-url ws://localhost:8000/ws
    python simulator/fake_device.py --device-id AA:BB:CC:DD:EE:FF --backend-url ws://localhost:8000/ws --failure-mode timeout
"""
import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field

try:
    import websockets
except ImportError:
    print("ERROR: websockets package required. Install with: pip install websockets")
    sys.exit(1)


@dataclass
class DeviceState:
    light_power: bool = False
    brightness: int = 50
    color: str = "#FFD27D"
    mode: str = "NORMAL"
    volume: int = 60
    is_playing_music: bool = False


@dataclass
class FakeDevice:
    device_id: str
    backend_url: str
    auth_token: str = "lamp_dev_token_a7f3b2c1e9d4"
    failure_mode: str | None = None
    state: DeviceState = field(default_factory=DeviceState)
    session_id: str | None = None
    connected: bool = False
    ws: object = None

    def log(self, event: str, **kwargs):
        ts = datetime.now(timezone.utc).isoformat()
        data = {"timestamp": ts, "event": event, "device_id": self.device_id, **kwargs}
        print(json.dumps(data))

    async def connect(self):
        """Connect to backend and complete handshake."""
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Protocol-Version": "1",
            "Device-Id": self.device_id,
            "Client-Id": str(uuid.uuid4()),
        }

        self.log("connecting", url=self.backend_url)
        self.ws = await websockets.connect(self.backend_url, additional_headers=headers)
        self.log("websocket_connected")

        # Send hello
        hello = {
            "type": "hello",
            "version": 1,
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": 16000,
                "channels": 1,
                "frame_duration": 60,
            },
        }
        await self.ws.send(json.dumps(hello))
        self.log("hello_sent")

        # Wait for server hello
        response = await asyncio.wait_for(self.ws.recv(), timeout=10)
        server_hello = json.loads(response)
        if server_hello.get("type") == "hello" and server_hello.get("transport") == "websocket":
            self.session_id = server_hello.get("session_id")
            self.connected = True
            self.log("handshake_complete", session_id=self.session_id)
        else:
            self.log("handshake_failed", response=server_hello)
            raise RuntimeError("Handshake failed")

    async def send_heartbeat(self):
        """Send periodic heartbeat."""
        while self.connected:
            await asyncio.sleep(30)
            if self.connected and self.ws:
                # Heartbeat is sent via REST API in real device, but we simulate via WS
                self.log("heartbeat_sent")

    async def listen_for_messages(self):
        """Listen for incoming messages from server."""
        try:
            async for message in self.ws:
                if isinstance(message, bytes):
                    # Binary audio frame from server (TTS)
                    self.log("tts_audio_received", size=len(message))
                else:
                    await self._handle_json_message(message)
        except websockets.ConnectionClosed:
            self.log("connection_closed")
            self.connected = False

    async def _handle_json_message(self, raw: str):
        """Handle incoming JSON message."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            self.log("invalid_json_received", raw=raw[:100])
            return

        msg_type = msg.get("type") or msg.get("messageType")

        if msg_type == "stt":
            self.log("stt_result", text=msg.get("text"))

        elif msg_type == "tts":
            state = msg.get("state")
            self.log("tts_control", state=state, text=msg.get("text"))

        elif msg_type == "llm":
            self.log("llm_emotion", emotion=msg.get("emotion"), text=msg.get("text"))

        elif msg_type == "COMMAND" or msg.get("messageType") == "COMMAND":
            await self._handle_command(msg)

        elif msg_type == "alert":
            self.log("alert_received", status=msg.get("status"), message=msg.get("message"))

        elif msg_type == "system":
            self.log("system_command", command=msg.get("command"))

        else:
            self.log("unknown_message", type=msg_type)

    async def _handle_command(self, msg: dict):
        """Handle a command from the server."""
        command_id = msg.get("commandId")
        command_type = msg.get("type")
        payload = msg.get("payload", {})

        self.log("command_received", command_id=command_id, type=command_type, payload=payload)

        # Simulate failure modes
        if self.failure_mode == "timeout":
            self.log("simulating_timeout", command_id=command_id)
            return  # Don't send ACK

        if self.failure_mode == "command_failed":
            ack = self._build_ack(command_id, "FAILED", error="simulated_failure")
            await self.ws.send(json.dumps(ack))
            self.log("command_ack_sent", command_id=command_id, status="FAILED")
            return

        # Process command and update state
        self._apply_command(command_type, payload)

        # Send ACK
        ack = self._build_ack(command_id, "SUCCESS")
        await self.ws.send(json.dumps(ack))
        self.log("command_ack_sent", command_id=command_id, status="SUCCESS", state=self._state_dict())

    def _apply_command(self, command_type: str, payload: dict):
        """Apply command to internal state."""
        if command_type == "TURN_ON_LIGHT":
            self.state.light_power = True
        elif command_type == "TURN_OFF_LIGHT":
            self.state.light_power = False
        elif command_type == "SET_BRIGHTNESS":
            self.state.brightness = payload.get("brightness", self.state.brightness)
        elif command_type == "CHANGE_LIGHT_MODE":
            self.state.mode = payload.get("mode", self.state.mode)
        elif command_type == "PLAY_MUSIC":
            self.state.is_playing_music = True
        elif command_type == "STOP_MUSIC":
            self.state.is_playing_music = False

        self.log("state_updated", state=self._state_dict())

    def _build_ack(self, command_id: str, status: str, error: str | None = None) -> dict:
        return {
            "messageType": "COMMAND_ACK",
            "commandId": command_id,
            "deviceId": self.device_id,
            "status": status,
            "state": self._state_dict(),
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _state_dict(self) -> dict:
        return {
            "lightPower": self.state.light_power,
            "brightness": self.state.brightness,
            "mode": self.state.mode,
            "isPlayingMusic": self.state.is_playing_music,
        }

    async def send_text_as_voice(self, text: str):
        """Simulate voice input by sending text through the listen protocol."""
        if not self.connected or not self.ws:
            self.log("not_connected")
            return

        # Send listen start
        await self.ws.send(json.dumps({
            "session_id": self.session_id,
            "type": "listen",
            "state": "start",
            "mode": "auto",
        }))

        # In a real device, we'd send Opus audio frames here
        # For text simulation, we just send listen stop immediately
        await asyncio.sleep(0.1)

        await self.ws.send(json.dumps({
            "session_id": self.session_id,
            "type": "listen",
            "state": "stop",
        }))

        self.log("text_sent_as_voice", text=text)

    async def interactive_mode(self):
        """Interactive mode: type text to simulate voice input."""
        print(f"\n{'='*60}")
        print(f"  Fake Device Simulator - Interactive Mode")
        print(f"  Device ID: {self.device_id}")
        print(f"  Session:   {self.session_id}")
        print(f"  Type text to simulate voice input, 'quit' to exit")
        print(f"  'state' to show current state")
        print(f"{'='*60}\n")

        loop = asyncio.get_event_loop()
        while self.connected:
            try:
                text = await loop.run_in_executor(None, input, "You> ")
                text = text.strip()
                if not text:
                    continue
                if text.lower() == "quit":
                    break
                if text.lower() == "state":
                    print(f"  State: {json.dumps(self._state_dict(), indent=2)}")
                    continue
                await self.send_text_as_voice(text)
            except (EOFError, KeyboardInterrupt):
                break

    async def run(self, interactive: bool = True):
        """Main run loop."""
        try:
            await self.connect()

            tasks = [
                asyncio.create_task(self.listen_for_messages()),
                asyncio.create_task(self.send_heartbeat()),
            ]

            if interactive:
                tasks.append(asyncio.create_task(self.interactive_mode()))

            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            self.log("error", error=str(e))
        finally:
            self.connected = False
            if self.ws:
                await self.ws.close()
            self.log("disconnected")


def main():
    parser = argparse.ArgumentParser(description="Fake Device Simulator for Lamp Chạm")
    parser.add_argument("--device-id", default="AA:BB:CC:DD:EE:FF", help="Device MAC address")
    parser.add_argument("--backend-url", default="ws://localhost:8000/ws", help="Backend WebSocket URL")
    parser.add_argument("--auth-token", default="lamp_dev_token_a7f3b2c1e9d4", help="Device auth token")
    parser.add_argument(
        "--failure-mode",
        choices=["offline", "timeout", "command_failed", "invalid_payload", "audio_playback_failed"],
        help="Simulate a failure mode",
    )
    parser.add_argument("--no-interactive", action="store_true", help="Disable interactive mode")

    args = parser.parse_args()

    device = FakeDevice(
        device_id=args.device_id,
        backend_url=args.backend_url,
        auth_token=args.auth_token,
        failure_mode=args.failure_mode,
    )

    asyncio.run(device.run(interactive=not args.no_interactive))


if __name__ == "__main__":
    main()
