from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.infra.database import check_db_connectivity, create_tables, dispose_engine
from app.api.routes_device import router as device_router
from app.api.routes_health import router as health_router
from app.api.routes_websocket import router as websocket_router
from app.services.background_tasks import start_background_tasks, stop_background_tasks

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
    start_background_tasks()
    logger.info("server_started", port=settings.server_port, database="connected")

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
