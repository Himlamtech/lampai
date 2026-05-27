from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Required
    openai_api_key: str
    openai_base_url: str = "https://api.yescale.io/v1"
    database_url: str
    device_auth_token: str

    # Server
    language: str = "vi"
    log_level: str = "INFO"
    server_port: int = 8000

    # AI Models
    llm_model: str = "gpt-4.1-nano"
    stt_model: str = "gpt-4o-transcribe"
    tts_model: str = "tts-1"
    tts_voice: str = "nova"
    tts_speed: float = 1.0

    # Timeouts
    hello_timeout_seconds: int = 10
    command_timeout_seconds: int = 5
    heartbeat_timeout_seconds: int = 90
    max_audio_buffer_seconds: int = 60
    max_conversation_context: int = 10

    # Timezone
    timezone: str = "Asia/Ho_Chi_Minh"

    # Admin
    admin_username: str = "admin"
    admin_password: str = "changeme"
    admin_jwt_secret: str = "change-this-secret"
    admin_jwt_expiry_hours: int = 24

    # File Upload
    upload_dir: str = "./uploads/music"
    max_upload_size_mb: int = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
