"""Persistence layer for ResearchReport (SQLite) + Chroma indexing."""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.logging import logger
from models.database import AsyncSessionLocal, ReportORM, WatchlistORM
from models.schemas import ResearchReport
from services.vectorstore import get_vector_store


class ReportRepository:
    """CRUD for reports."""

    @staticmethod
    async def save(report: ResearchReport) -> int:
        async with AsyncSessionLocal() as session:  # type: AsyncSession
            try:
                row = ReportORM(
                    symbol=report.symbol,
                    market=report.market.value if report.market else "未知",
                    title=report.title,
                    executive_summary=report.executive_summary,
                    recommendation=report.recommendation,
                    target_price=report.target_price,
                    confidence=report.confidence,
                    full_json=report.model_dump_json(),
                    language=report.request.language,
                    created_at=report.created_at or datetime.utcnow(),
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                logger.info("Saved report id={} symbol={}", row.id, row.symbol)

                vs = get_vector_store()
                vs.add(
                    doc_id=str(row.id),
                    text=f"{report.title}\n{report.executive_summary}\n{report.fundamental.summary if report.fundamental else ''}",
                    metadata={
                        "symbol": report.symbol,
                        "recommendation": report.recommendation,
                        "created_at": row.created_at.isoformat(),
                    },
                )
                return int(row.id)
            except Exception as e:  # noqa: BLE001
                await session.rollback()
                logger.exception("Failed to save report: {}", e)
                raise

    @staticmethod
    async def list_recent(limit: int = 20, symbol: Optional[str] = None) -> List[ResearchReport]:
        async with AsyncSessionLocal() as session:
            stmt = select(ReportORM).order_by(desc(ReportORM.created_at)).limit(limit)
            if symbol:
                stmt = (
                    select(ReportORM)
                    .where(ReportORM.symbol == symbol)
                    .order_by(desc(ReportORM.created_at))
                    .limit(limit)
                )
            res = await session.execute(stmt)
            rows = res.scalars().all()
            out: List[ResearchReport] = []
            for r in rows:
                try:
                    data = json.loads(r.full_json)
                    data["id"] = r.id
                    out.append(ResearchReport.model_validate(data))
                except Exception:  # noqa: BLE001
                    continue
            return out

    @staticmethod
    async def get(report_id: int) -> Optional[ResearchReport]:
        async with AsyncSessionLocal() as session:
            row = await session.get(ReportORM, report_id)
            if not row:
                return None
            data = json.loads(row.full_json)
            data["id"] = row.id
            return ResearchReport.model_validate(data)


class WatchlistRepository:
    @staticmethod
    async def add(symbol: str, name: Optional[str] = None, market: str = "未知", note: str = "") -> WatchlistORM:
        async with AsyncSessionLocal() as session:
            existing = await session.execute(
                select(WatchlistORM).where(WatchlistORM.symbol == symbol)
            )
            row = existing.scalar_one_or_none()
            if row:
                return row
            row = WatchlistORM(symbol=symbol, name=name, market=market, note=note)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def list_all() -> List[WatchlistORM]:
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(WatchlistORM).order_by(WatchlistORM.id))
            return list(res.scalars().all())

    @staticmethod
    async def remove(symbol: str) -> bool:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(WatchlistORM).where(WatchlistORM.symbol == symbol)
            )
            row = res.scalar_one_or_none()
            if not row:
                return False
            await session.delete(row)
            await session.commit()
            return True
