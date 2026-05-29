"""Async SQLAlchemy database setup with ORM models for reports & watchlist."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings
from config.logging import logger


def _utcnow_naive() -> datetime:
    """Naive UTC now. Replaces the legacy deprecated naive helper while
    preserving the original semantics (column type is plain DateTime,
    not DateTime(timezone=True))."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class ReportORM(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), index=True, nullable=False)
    market = Column(String(16), default="未知")
    title = Column(String(255), nullable=False)
    executive_summary = Column(Text, nullable=False)
    recommendation = Column(String(16), default="观望")
    target_price = Column(Float, nullable=True)
    confidence = Column(Float, default=0.0)
    full_json = Column(Text, nullable=False)  # serialized ResearchReport
    language = Column(String(8), default="zh-CN")
    created_at = Column(DateTime, default=_utcnow_naive, index=True)


class WatchlistORM(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=True)
    market = Column(String(16), default="未知")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow_naive)


_data_dir = Path(settings.project_root) / "data"
_data_dir.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """Create tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialised at {}", settings.database_url)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields an AsyncSession."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


__all__ = [
    "Base",
    "ReportORM",
    "WatchlistORM",
    "engine",
    "AsyncSessionLocal",
    "init_db",
    "get_session",
    "select",
]
