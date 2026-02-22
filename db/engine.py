import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import DATABASE_URL
from db.models import Base

os.makedirs("data", exist_ok=True)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add columns introduced after initial schema (safe to run repeatedly)
        for stmt in [
            "ALTER TABLE settings ADD COLUMN notify_taken BOOLEAN NOT NULL DEFAULT 1",
            "ALTER TABLE settings ADD COLUMN chat_id INTEGER",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # Column already exists


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
