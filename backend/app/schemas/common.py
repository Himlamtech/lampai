from pydantic import BaseModel
from typing import Generic, TypeVar
from datetime import datetime, timezone

T = TypeVar("T")


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict = {}
    timestamp: str = ""

    def __init__(self, **data):
        if not data.get("timestamp"):
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        super().__init__(**data)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class HealthResponse(BaseModel):
    status: str
    database: str
    active_connections: int
    uptime_seconds: float
    version: str = "0.1.0"
