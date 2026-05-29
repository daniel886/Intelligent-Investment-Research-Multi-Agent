"""FastAPI HTTP routes."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from config.logging import logger
from models.schemas import ResearchReport, ResearchRequest
from services.repository import ReportRepository, WatchlistRepository
from services.scheduler import run_daily_report
from services.vectorstore import get_vector_store
from workflows.research_workflow import get_workflow


router = APIRouter()


# ----------------- Request / Response models -----------------
class ResearchAPIRequest(BaseModel):
    query: str = Field(..., description="自然语言指令")
    symbols: Optional[List[str]] = None
    language: str = "zh-CN"
    deep: bool = False


class WatchlistAddRequest(BaseModel):
    symbol: str
    name: Optional[str] = None
    market: str = "未知"
    note: str = ""


class HealthResponse(BaseModel):
    status: str
    time: datetime


# ----------------- Routes -----------------
@router.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", time=datetime.utcnow())


@router.post("/research", response_model=List[ResearchReport], tags=["research"])
async def run_research(payload: ResearchAPIRequest) -> List[ResearchReport]:
    """Execute multi-agent research synchronously and persist results."""
    request = ResearchRequest(
        query=payload.query,
        symbols=payload.symbols,
        language=payload.language,  # type: ignore
        deep=payload.deep,
    )
    workflow = get_workflow()
    try:
        reports = await workflow.run(request)
    except Exception as e:  # noqa: BLE001
        logger.exception("Research failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
    saved: List[ResearchReport] = []
    for r in reports:
        try:
            rid = await ReportRepository.save(r)
            r.id = rid
        except Exception as e:  # noqa: BLE001
            logger.warning("save report failed: {}", e)
        saved.append(r)
    return saved


@router.get("/reports", response_model=List[ResearchReport], tags=["reports"])
async def list_reports(
    limit: int = Query(20, ge=1, le=100),
    symbol: Optional[str] = None,
) -> List[ResearchReport]:
    return await ReportRepository.list_recent(limit=limit, symbol=symbol)


@router.get("/reports/{report_id}", response_model=ResearchReport, tags=["reports"])
async def get_report(report_id: int) -> ResearchReport:
    r = await ReportRepository.get(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    return r


@router.get("/reports/search/semantic", tags=["reports"])
async def semantic_search(q: str, n: int = 5) -> dict:
    vs = get_vector_store()
    return {"query": q, "results": vs.query(q, n_results=n)}


@router.post("/watchlist", tags=["watchlist"])
async def add_watch(payload: WatchlistAddRequest) -> dict:
    row = await WatchlistRepository.add(
        symbol=payload.symbol,
        name=payload.name,
        market=payload.market,
        note=payload.note,
    )
    return {"id": row.id, "symbol": row.symbol}


@router.get("/watchlist", tags=["watchlist"])
async def list_watch() -> List[dict]:
    rows = await WatchlistRepository.list_all()
    return [
        {"id": r.id, "symbol": r.symbol, "name": r.name, "market": r.market, "note": r.note}
        for r in rows
    ]


@router.delete("/watchlist/{symbol}", tags=["watchlist"])
async def remove_watch(symbol: str) -> dict:
    ok = await WatchlistRepository.remove(symbol)
    if not ok:
        raise HTTPException(404, "Symbol not in watchlist")
    return {"removed": symbol}


@router.post("/scheduler/run-now", tags=["scheduler"])
async def run_now(background: BackgroundTasks) -> dict:
    background.add_task(run_daily_report)
    return {"status": "scheduled"}
