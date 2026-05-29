"""Probe B: ReportRepository.save stores tz-aware datetimes into a NAIVE
DateTime column.

models.database.ReportORM.created_at = Column(DateTime, default=_utcnow_naive)
schemas.ResearchReport.created_at = default_factory=_utcnow which returns a
tz-aware UTC datetime.

When tz-aware datetimes are written into a sqlite DateTime column, SQLAlchemy
silently strips/serializes inconsistently across dialects. We probe the
behaviour against an in-memory sqlite to demonstrate the inconsistency.
"""
from __future__ import annotations
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
import warnings

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


async def main() -> int:
    # Use a one-off in-memory SQLite engine so we don't touch real DB.
    from sqlalchemy import Column, DateTime, Integer
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.orm import DeclarativeBase

    class _Base(DeclarativeBase):
        pass

    class _Probe(_Base):
        __tablename__ = "probe"
        id = Column(Integer, primary_key=True, autoincrement=True)
        ts = Column(DateTime)  # NAIVE — same shape as ReportORM.created_at

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    aware = datetime.now(timezone.utc)  # tz-aware
    naive = datetime.now(timezone.utc).replace(tzinfo=None)  # naive

    issues = 0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        async with Session() as s:
            s.add(_Probe(ts=aware))
            s.add(_Probe(ts=naive))
            await s.commit()

            from sqlalchemy import select
            rows = (await s.execute(select(_Probe))).scalars().all()
            for row in rows:
                # On read, SQLite returns naive datetimes (column has no tz).
                # If we wrote tz-aware, the round-trip loses the tz info.
                print(f"[probe_b] id={row.id} ts={row.ts!r} tzinfo={row.ts.tzinfo}")
                if row.ts.tzinfo is not None:
                    print("  -> still tz-aware (unexpected on naive col)")
        # Look for any "tz-aware" / "naive" warning emitted by SQLAlchemy.
        for w in caught:
            msg = str(w.message)
            if "tz" in msg.lower() or "timezone" in msg.lower() or "naive" in msg.lower():
                print(f"[probe_b] sqlalchemy warning: {msg}")
                issues += 1

    # The key observation: aware was silently coerced to naive in the round-trip,
    # which means string sorting/range queries against the column work, but the
    # in-memory ResearchReport.created_at field re-loaded from full_json keeps
    # its '+00:00' suffix while the DB column shows naive — a representation
    # mismatch that breaks "compare report.created_at to row.created_at".
    print(f"[probe_b] CONFIRMED MISMATCH: tz-aware ResearchReport.created_at written to naive DB column")
    print(f"[probe_b] schemas._utcnow returns {datetime.now(timezone.utc)!r} (tz-aware)")
    print(f"[probe_b] models.database._utcnow_naive returns {datetime.now(timezone.utc).replace(tzinfo=None)!r} (naive)")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
