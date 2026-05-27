"""Background tasks for periodic operations."""
import asyncio
from app.core.config import settings
from app.core.logging import get_logger
from app.infra.database import get_session_factory
from app.services.device_service import DeviceService

logger = get_logger("background_tasks")

_heartbeat_task: asyncio.Task | None = None


async def heartbeat_monitor_loop():
    """Periodically check for stale devices and mark them offline."""
    logger.info("heartbeat_monitor_started", interval_seconds=30)
    while True:
        try:
            await asyncio.sleep(30)
            factory = get_session_factory()
            async with factory() as session:
                service = DeviceService(session)
                stale_ids = await service.mark_offline_stale_devices()
                if stale_ids:
                    logger.info("stale_devices_marked_offline", count=len(stale_ids), device_ids=stale_ids)
        except asyncio.CancelledError:
            logger.info("heartbeat_monitor_stopped")
            break
        except Exception as e:
            logger.error("heartbeat_monitor_error", error=str(e))
            await asyncio.sleep(5)  # Brief pause before retry


def start_background_tasks():
    """Start all background tasks."""
    global _heartbeat_task
    _heartbeat_task = asyncio.create_task(heartbeat_monitor_loop())
    logger.info("background_tasks_started")


async def stop_background_tasks():
    """Stop all background tasks."""
    global _heartbeat_task
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
        _heartbeat_task = None
    logger.info("background_tasks_stopped")
