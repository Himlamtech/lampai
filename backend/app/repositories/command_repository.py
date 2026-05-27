"""Command repository for persisting command logs."""
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import CommandModel
from app.domain.commands import CommandStatus


class CommandRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        command_id: str,
        device_id: str,
        command_type: str,
        payload: dict,
    ) -> CommandModel:
        command = CommandModel(
            command_id=command_id,
            device_id=device_id,
            type=command_type,
            payload=payload,
            status=CommandStatus.PENDING.value,
        )
        self.session.add(command)
        await self.session.commit()
        await self.session.refresh(command)
        return command

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        failure_reason: str | None = None,
    ) -> bool:
        values: dict = {"status": status.value}
        now = datetime.now(timezone.utc)
        if status == CommandStatus.SENT:
            values["sent_at"] = now
        elif status in (CommandStatus.SUCCESS, CommandStatus.FAILED, CommandStatus.TIMED_OUT):
            values["acked_at"] = now
        if failure_reason:
            values["failure_reason"] = failure_reason

        result = await self.session.execute(
            update(CommandModel)
            .where(CommandModel.command_id == command_id)
            .values(**values)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def get_by_command_id(self, command_id: str) -> CommandModel | None:
        result = await self.session.execute(
            select(CommandModel).where(CommandModel.command_id == command_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_commands(self, device_id: str) -> list[CommandModel]:
        result = await self.session.execute(
            select(CommandModel).where(
                CommandModel.device_id == device_id,
                CommandModel.status.in_([CommandStatus.PENDING.value, CommandStatus.SENT.value]),
            )
        )
        return list(result.scalars().all())

    async def get_by_device(self, device_id: str, limit: int = 50) -> list[CommandModel]:
        result = await self.session.execute(
            select(CommandModel)
            .where(CommandModel.device_id == device_id)
            .order_by(CommandModel.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_pending_as_failed(self, device_id: str, reason: str) -> int:
        """Mark all pending/sent commands for a device as FAILED."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(CommandModel)
            .where(
                CommandModel.device_id == device_id,
                CommandModel.status.in_([CommandStatus.PENDING.value, CommandStatus.SENT.value]),
            )
            .values(status=CommandStatus.FAILED.value, failure_reason=reason, acked_at=now)
        )
        await self.session.commit()
        return result.rowcount
