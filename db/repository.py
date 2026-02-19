from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import OrderLog, Settings


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> Optional[Settings]:
        result = await self._session.execute(select(Settings).where(Settings.id == 1))
        return result.scalar_one_or_none()

    async def get_or_create(self) -> Settings:
        settings = await self.get()
        if settings is None:
            settings = Settings(id=1)
            self._session.add(settings)
            await self._session.commit()
            await self._session.refresh(settings)
        return settings

    async def update(self, **kwargs) -> Settings:
        settings = await self.get_or_create()
        for key, value in kwargs.items():
            setattr(settings, key, value)
        await self._session.commit()
        await self._session.refresh(settings)
        return settings


class OrderLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order_slug: str, amount: Optional[float], status: str) -> OrderLog:
        entry = OrderLog(
            order_slug=order_slug,
            amount=amount,
            status=status,
            taken_at=datetime.utcnow(),
        )
        self._session.add(entry)
        await self._session.commit()
        return entry

    async def count_taken(self) -> int:
        result = await self._session.execute(
            select(func.count()).where(OrderLog.status == "taken")
        )
        return result.scalar_one()

    async def count_failed(self) -> int:
        result = await self._session.execute(
            select(func.count()).where(OrderLog.status == "failed")
        )
        return result.scalar_one()

    async def last_entries(self, limit: int = 5) -> List[OrderLog]:
        result = await self._session.execute(
            select(OrderLog).order_by(OrderLog.taken_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
