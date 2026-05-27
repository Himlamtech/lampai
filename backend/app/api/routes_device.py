from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database import get_session
from app.services.device_service import DeviceService
from app.schemas.device import DeviceRegisterRequest, DeviceStateUpdateRequest
from app.schemas.common import ErrorResponse
from app.core.errors import ValidationError

router = APIRouter(prefix="/api/devices", tags=["devices"])


def get_device_service(session: AsyncSession = Depends(get_session)) -> DeviceService:
    return DeviceService(session)


@router.post("/register")
async def register_device(
    request: DeviceRegisterRequest,
    service: DeviceService = Depends(get_device_service),
):
    try:
        state = await service.register(request.device_id)
        return {"status": "ok", "device": state.model_dump()}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.message)


@router.post("/{device_id}/heartbeat")
async def device_heartbeat(
    device_id: str,
    service: DeviceService = Depends(get_device_service),
):
    try:
        success = await service.heartbeat(device_id)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"status": "ok"}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.message)


@router.get("/{device_id}/state")
async def get_device_state(
    device_id: str,
    service: DeviceService = Depends(get_device_service),
):
    try:
        state = await service.get_state(device_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return state.model_dump()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.message)


@router.patch("/{device_id}/state")
async def update_device_state(
    device_id: str,
    request: DeviceStateUpdateRequest,
    service: DeviceService = Depends(get_device_service),
):
    try:
        updates = request.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        state = await service.update_state(device_id, updates)
        if state is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return state.model_dump()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.message)
