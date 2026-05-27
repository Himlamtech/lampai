"""Voice processing REST API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database import get_session
from app.services.voice_pipeline import VoicePipeline, PipelineResult
from app.services.stt_service import OpenAISTTService
from app.services.tts_service import OpenAITTSService
from app.services.llm_service import OpenAILLMService
from app.services.intent_service import IntentParser
from app.services.command_service import CommandDispatcher
from app.services.device_service import DeviceService
from app.repositories.conversation_repository import ConversationRepository
from app.domain.intents import HARDWARE_INTENTS
from app.core.errors import DeviceOfflineError, ProviderError
from app.core.logging import get_logger

logger = get_logger("routes_voice")

router = APIRouter(prefix="/api/voice", tags=["voice"])


class ProcessTextRequest(BaseModel):
    text: str
    device_id: str
    session_id: str = "api-session"


class ProcessTextResponse(BaseModel):
    user_text: str
    intent: str
    params: dict = {}
    ai_response: str
    command_sent: bool = False
    command_id: str | None = None
    error: str | None = None
    latency_ms: int = 0
    stage_latencies: dict = {}


@router.post("/process-text", response_model=ProcessTextResponse)
async def process_text(
    request: ProcessTextRequest,
    db_session: AsyncSession = Depends(get_session),
):
    """Process text through the voice pipeline (skip STT)."""
    # Build pipeline with real services
    pipeline = VoicePipeline(
        stt_service=OpenAISTTService(),
        tts_service=OpenAITTSService(),
        llm_service=OpenAILLMService(),
        intent_parser=IntentParser(),
    )

    # Get conversation context
    conv_repo = ConversationRepository(db_session)
    context = await conv_repo.get_recent_context(request.session_id, limit=10)

    # Process text
    result = await pipeline.process_text(
        text=request.text,
        device_id=request.device_id,
        session_id=request.session_id,
        context=context,
    )

    # Dispatch command if hardware intent
    command_id = None
    if result.intent and result.intent.intent in HARDWARE_INTENTS:
        try:
            dispatcher = CommandDispatcher(db_session)
            # Ensure device exists
            device_service = DeviceService(db_session)
            device = await device_service.get_state(request.device_id)
            if device is None:
                await device_service.register(request.device_id)

            command = await dispatcher.dispatch(request.device_id, result.intent)
            command_id = command.commandId
        except DeviceOfflineError:
            pass  # Command stored as failed, continue with response
        except Exception as e:
            logger.error("command_dispatch_error", error=str(e))

    # Store conversation
    await conv_repo.create(
        device_id=request.device_id,
        session_id=request.session_id,
        user_text=result.user_text,
        ai_response=result.ai_response,
        intent=result.intent.intent.value if result.intent else "UNKNOWN",
        latency_ms=result.total_latency_ms,
        stage_latencies=result.stage_latencies,
    )

    return ProcessTextResponse(
        user_text=result.user_text,
        intent=result.intent.intent.value if result.intent else "UNKNOWN",
        params=result.intent.params if result.intent else {},
        ai_response=result.ai_response,
        command_sent=command_id is not None,
        command_id=command_id,
        error=result.error,
        latency_ms=result.total_latency_ms,
        stage_latencies=result.stage_latencies,
    )


class TTSRequest(BaseModel):
    text: str
    voice: str = "nova"
    speed: float = 1.0


@router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """Convert text to speech audio (returns opus audio bytes)."""
    tts = OpenAITTSService()
    try:
        audio_bytes = await tts.synthesize(request.text, voice=request.voice, speed=request.speed)
        return Response(content=audio_bytes, media_type="audio/ogg")
    except ProviderError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe uploaded audio file to text (Vietnamese by default)."""
    try:
        audio_data = await file.read()
        if not audio_data:
            raise HTTPException(status_code=400, detail="Empty audio file")

        from openai import AsyncOpenAI
        from app.core.config import settings

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

        # Use whisper-1 with Vietnamese language hint for best accuracy
        transcript = await client.audio.transcriptions.create(
            model=settings.stt_model,
            file=(file.filename or "audio.webm", audio_data, file.content_type or "audio/webm"),
            language="vi",
            prompt="Bật đèn, tắt đèn, tăng sáng, giảm sáng, phát nhạc, dừng nhạc, mấy giờ, thời tiết, chế độ ngủ.",
        )

        text = transcript.text.strip()
        logger.info("transcribe_complete", text_length=len(text), file_size=len(audio_data))
        return {"text": text}

    except Exception as e:
        logger.error("transcribe_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
