from datetime import datetime, timezone


class LampAIError(Exception):
    def __init__(self, error: str, message: str, details: dict | None = None):
        self.error = error
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()
        super().__init__(message)


class DeviceOfflineError(LampAIError):
    def __init__(self, device_id: str):
        super().__init__(
            error="device_offline",
            message=f"Device {device_id} is offline",
            details={"device_id": device_id},
        )


class ValidationError(LampAIError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(error="validation_error", message=message, details=details)


class CommandTimeoutError(LampAIError):
    def __init__(self, command_id: str):
        super().__init__(
            error="command_timeout",
            message=f"Command {command_id} timed out",
            details={"command_id": command_id},
        )


class AuthenticationError(LampAIError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(error="auth_error", message=message)


class ProviderError(LampAIError):
    def __init__(self, provider: str, message: str):
        super().__init__(
            error="provider_error",
            message=message,
            details={"provider": provider},
        )
