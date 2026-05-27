import time
from fastapi import APIRouter

from app.infra.database import check_db_connectivity
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])

_start_time = time.time()


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    db_ok = await check_db_connectivity()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        database="connected" if db_ok else "disconnected",
        active_connections=0,  # Will be updated when WebSocket manager is integrated
        uptime_seconds=round(time.time() - _start_time, 1),
    )
