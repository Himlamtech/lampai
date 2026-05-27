"""Conversation history repository."""
from datetime import datetime, timezone
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import ConversationModel
from app.services.llm_service import ConversationTurn


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        device_id: str,
        session_id: str,
        user_text: str,
        ai_response: str | None,
        intent: str,
        latency_ms: int | None = None,
        stage_latencies: dict | None = None,
    ) -> ConversationModel:
        record = ConversationModel(
            device_id=device_id,
            session_id=session_id,
            user_text=user_text,
            ai_response=ai_response,
            intent=intent,
            latency_ms=latency_ms,
            stage_latencies=stage_latencies,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_recent_context(
        self, session_id: str, limit: int = 10
    ) -> list[ConversationTurn]:
        """Get recent conversation turns for context."""
        result = await self.session.execute(
            select(ConversationModel)
            .where(ConversationModel.session_id == session_id)
            .order_by(ConversationModel.created_at.desc())
            .limit(limit)
        )
        records = list(result.scalars().all())
        records.reverse()  # Oldest first

        turns = []
        for r in records:
            turns.append(ConversationTurn(role="user", content=r.user_text))
            if r.ai_response:
                turns.append(ConversationTurn(role="assistant", content=r.ai_response))
        return turns

    async def get_by_device(
        self, device_id: str, limit: int = 50, offset: int = 0
    ) -> list[ConversationModel]:
        result = await self.session.execute(
            select(ConversationModel)
            .where(ConversationModel.device_id == device_id)
            .order_by(ConversationModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
