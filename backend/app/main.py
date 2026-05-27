from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.infra.database import check_db_connectivity, create_tables, dispose_engine, get_session_factory
from app.api.routes_device import router as device_router
from app.api.routes_health import router as health_router
from app.api.routes_websocket import router as websocket_router
from app.api.routes_voice import router as voice_router
from app.api.routes_admin import router as admin_router
from app.services.background_tasks import start_background_tasks, stop_background_tasks
from app.services.music_service import MusicService

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(
        "server_starting",
        port=settings.server_port,
        language=settings.language,
        log_level=settings.log_level,
    )

    db_ok = await check_db_connectivity()
    if not db_ok:
        logger.error("database_unreachable_at_startup")
        raise RuntimeError("Database is unreachable. Check DATABASE_URL configuration.")

    await create_tables()

    # Seed music catalog
    factory = get_session_factory()
    async with factory() as session:
        music_service = MusicService(session)
        await music_service.seed_catalog()

    start_background_tasks()
    logger.info("server_started", port=settings.server_port, database="connected")

    yield

    # Shutdown
    logger.info("server_shutting_down")
    await stop_background_tasks()
    await dispose_engine()
    logger.info("server_stopped")

    yield

    # Shutdown
    logger.info("server_shutting_down")
    await stop_background_tasks()
    await dispose_engine()
    logger.info("server_stopped")


app = FastAPI(
    title="Lamp Chạm AI Backend",
    description="XiaoZhi protocol WebSocket server for LunaLamp smart bedside lamp",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(device_router)
app.include_router(health_router)
app.include_router(websocket_router)
app.include_router(voice_router)
app.include_router(admin_router)

# Serve static admin dashboard and test environment
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/admin", StaticFiles(directory=str(static_dir / "admin"), html=True), name="admin")
    if (static_dir / "test").exists():
        app.mount("/test", StaticFiles(directory=str(static_dir / "test"), html=True), name="test")
