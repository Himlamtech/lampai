"""Admin API routes — authentication, device management, config, conversations."""
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, text
from datetime import datetime, timezone

from app.infra.database import get_session
from app.infra.models import DeviceModel, CommandModel, ConversationModel, MusicCatalogModel
from app.infra.websocket_manager import ws_manager
from app.services.admin_auth_service import authenticate_admin, verify_token, seed_admin_user
from app.services.device_service import DeviceService
from app.services.command_service import CommandDispatcher
from app.services.music_service import MusicService
from app.domain.intents import ParsedIntent, IntentType
from app.core.errors import AuthenticationError
from app.core.logging import get_logger

logger = get_logger("admin_api")

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Auth Models ---
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


# --- Auth Dependency ---
async def require_admin(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization[7:]
    try:
        username = verify_token(token)
        return username
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# --- Auth Endpoints ---
@router.post("/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest):
    try:
        token = authenticate_admin(request.username, request.password)
        return LoginResponse(token=token, username=request.username)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid credentials")


# --- Dashboard ---
@router.get("/dashboard")
async def dashboard_overview(
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    # Online device count
    online_result = await db.execute(
        select(func.count()).select_from(DeviceModel).where(DeviceModel.status == "ONLINE")
    )
    online_count = online_result.scalar() or 0

    # Total device count
    total_result = await db.execute(select(func.count()).select_from(DeviceModel))
    total_count = total_result.scalar() or 0

    # Active WebSocket connections
    active_connections = ws_manager.get_active_session_count()

    # Recent conversations (last 10)
    conv_result = await db.execute(
        select(ConversationModel)
        .order_by(ConversationModel.created_at.desc())
        .limit(10)
    )
    recent_conversations = [
        {
            "id": c.id,
            "device_id": c.device_id,
            "user_text": c.user_text,
            "ai_response": c.ai_response,
            "intent": c.intent,
            "latency_ms": c.latency_ms,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in conv_result.scalars().all()
    ]

    return {
        "online_devices": online_count,
        "total_devices": total_count,
        "active_connections": active_connections,
        "recent_conversations": recent_conversations,
    }


# --- Device Management ---
@router.get("/devices")
async def list_devices(
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(DeviceModel).order_by(DeviceModel.created_at.desc()))
    devices = [
        {
            "device_id": d.device_id,
            "status": d.status,
            "light_power": d.light_power,
            "brightness": d.brightness,
            "color": d.color,
            "mode": d.mode,
            "volume": d.volume,
            "is_playing_music": d.is_playing_music,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in result.scalars().all()
    ]
    return {"devices": devices}


@router.get("/devices/{device_id}")
async def get_device_detail(
    device_id: str,
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    service = DeviceService(db)
    state = await service.get_state(device_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return state.model_dump()


class AdminCommandRequest(BaseModel):
    type: str
    payload: dict = {}


@router.post("/devices/{device_id}/commands")
async def send_device_command(
    device_id: str,
    request: AdminCommandRequest,
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Send a test command to a device from admin panel."""
    if not ws_manager.is_device_online(device_id):
        raise HTTPException(status_code=409, detail="Device is offline")

    dispatcher = CommandDispatcher(db)
    intent = ParsedIntent(
        intent=IntentType(request.type) if request.type in IntentType.__members__ else IntentType.UNKNOWN,
        params=request.payload,
        source="admin",
    )
    try:
        command = await dispatcher.dispatch(device_id, intent)
        return {"command_id": command.commandId, "status": "SENT", "type": command.type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/commands")
async def get_device_commands(
    device_id: str,
    limit: int = 50,
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(CommandModel)
        .where(CommandModel.device_id == device_id)
        .order_by(CommandModel.created_at.desc())
        .limit(limit)
    )
    commands = [
        {
            "command_id": c.command_id,
            "type": c.type,
            "payload": c.payload,
            "status": c.status,
            "failure_reason": c.failure_reason,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "sent_at": c.sent_at.isoformat() if c.sent_at else None,
            "acked_at": c.acked_at.isoformat() if c.acked_at else None,
        }
        for c in result.scalars().all()
    ]
    return {"commands": commands}


# --- Conversations ---
class ConversationQuery(BaseModel):
    device_id: str | None = None
    search: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


@router.get("/conversations")
async def list_conversations(
    device_id: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    query = select(ConversationModel)
    count_query = select(func.count()).select_from(ConversationModel)

    if device_id:
        query = query.where(ConversationModel.device_id == device_id)
        count_query = count_query.where(ConversationModel.device_id == device_id)
    if search:
        search_filter = ConversationModel.user_text.ilike(f"%{search}%") | ConversationModel.ai_response.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(ConversationModel.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )

    conversations = [
        {
            "id": c.id,
            "device_id": c.device_id,
            "session_id": c.session_id,
            "user_text": c.user_text,
            "ai_response": c.ai_response,
            "intent": c.intent,
            "latency_ms": c.latency_ms,
            "stage_latencies": c.stage_latencies,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in result.scalars().all()
    ]

    total_pages = (total + page_size - 1) // page_size

    return {
        "items": conversations,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        delete(ConversationModel).where(ConversationModel.id == conversation_id)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


class BulkDeleteRequest(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    device_id: str | None = None


@router.post("/conversations/bulk-delete")
async def bulk_delete_conversations(
    request: BulkDeleteRequest,
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    query = delete(ConversationModel)
    if request.device_id:
        query = query.where(ConversationModel.device_id == request.device_id)
    if request.date_from:
        query = query.where(ConversationModel.created_at >= request.date_from)
    if request.date_to:
        query = query.where(ConversationModel.created_at <= request.date_to)

    result = await db.execute(query)
    await db.commit()
    return {"deleted_count": result.rowcount}


# --- Music Catalog ---
@router.get("/music")
async def list_music(
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    service = MusicService(db)
    tracks = await service.get_tracks()
    return {
        "tracks": [
            {
                "id": t.id,
                "title": t.title,
                "type": t.type,
                "source_url": t.source_url,
                "duration_seconds": t.duration_seconds,
                "is_default": t.is_default,
            }
            for t in tracks
        ]
    }


class AddTrackRequest(BaseModel):
    id: str
    title: str
    type: str
    source_url: str
    duration_seconds: int
    is_default: bool = False


@router.post("/music")
async def add_music_track(
    request: AddTrackRequest,
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    track = MusicCatalogModel(
        id=request.id,
        title=request.title,
        type=request.type.upper(),
        source_url=request.source_url,
        duration_seconds=request.duration_seconds,
        is_default=request.is_default,
    )
    db.add(track)
    await db.commit()
    return {"status": "created", "id": request.id}


@router.delete("/music/{track_id}")
async def delete_music_track(
    track_id: str,
    admin: str = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        delete(MusicCatalogModel).where(MusicCatalogModel.id == track_id)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Track not found")
    return {"status": "deleted"}


# --- Voice Config (simplified — stored in settings for now) ---
class VoiceConfigResponse(BaseModel):
    voice: str
    speed: float
    stt_language: str
    tts_language: str


@router.get("/voice-config")
async def get_voice_config(admin: str = Depends(require_admin)):
    from app.core.config import settings
    return VoiceConfigResponse(
        voice=settings.tts_voice,
        speed=settings.tts_speed,
        stt_language=settings.language,
        tts_language=settings.language,
    )


# --- System Instructions (simplified) ---
_system_instructions: str = ""
_instructions_history: list[dict] = []


@router.get("/instructions")
async def get_instructions(admin: str = Depends(require_admin)):
    return {"content": _system_instructions, "history_count": len(_instructions_history)}


class UpdateInstructionsRequest(BaseModel):
    content: str


@router.post("/instructions")
async def update_instructions(
    request: UpdateInstructionsRequest,
    admin: str = Depends(require_admin),
):
    global _system_instructions, _instructions_history
    _instructions_history.append({
        "content": _system_instructions,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    _system_instructions = request.content
    logger.info("system_instructions_updated", length=len(request.content))
    return {"status": "updated", "version": len(_instructions_history) + 1}


@router.get("/instructions/history")
async def get_instructions_history(admin: str = Depends(require_admin)):
    return {"history": _instructions_history}


INSTRUCTION_TEMPLATES = {
    "bedtime_companion": "Bạn là một người bạn đồng hành lúc đi ngủ. Hãy nói nhẹ nhàng, ấm áp, và giúp người dùng thư giãn. Gợi ý các bài tập thở, kể chuyện ngắn, hoặc phát nhạc ru khi được yêu cầu.",
    "study_buddy": "Bạn là một trợ lý học tập thông minh. Hãy giúp người dùng tập trung, nhắc nhở giờ nghỉ, và trả lời các câu hỏi kiến thức một cách ngắn gọn, dễ hiểu.",
    "meditation_guide": "Bạn là một hướng dẫn viên thiền định. Hãy nói chậm rãi, bình tĩnh, và hướng dẫn người dùng qua các bài tập chánh niệm và thở.",
    "general_assistant": "Bạn là trợ lý AI của đèn LunaLamp. Hãy trả lời ngắn gọn, thân thiện, và hữu ích. Bạn có thể điều khiển đèn, phát nhạc, và trả lời câu hỏi.",
}


@router.get("/instructions/templates")
async def get_instruction_templates(admin: str = Depends(require_admin)):
    return {"templates": [{"name": k, "content": v} for k, v in INSTRUCTION_TEMPLATES.items()]}
