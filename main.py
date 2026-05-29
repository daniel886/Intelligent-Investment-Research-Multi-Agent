"""Entry-point: starts the FastAPI server (and embedded scheduler)."""
from __future__ import annotations

import asyncio
import sys

import uvicorn

from config import settings
from config.logging import logger, setup_logging


def main() -> None:
    setup_logging()
    logger.info(
        "Starting Intelligent Investment Research Multi-Agent on {}:{} (env={})",
        settings.app_host,
        settings.app_port,
        settings.app_env,
    )
    uvicorn.run(
        "api.app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
        access_log=False,
    )


async def cli_research(query: str) -> None:
    """Quick CLI: `python main.py research "分析腾讯"`"""
    from models.database import init_db
    from models.schemas import ResearchRequest
    from services.repository import ReportRepository
    from workflows.research_workflow import get_workflow

    setup_logging()
    await init_db()
    workflow = get_workflow()
    reports = await workflow.run(ResearchRequest(query=query, language=settings.language))
    for r in reports:
        await ReportRepository.save(r)
        print("=" * 80)
        print(r.title)
        print(f"评级: {r.recommendation} | 目标价: {r.target_price} | 置信度: {r.confidence:.2f}")
        print(r.executive_summary)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "research":
        query = " ".join(sys.argv[2:]) or "分析苹果公司"
        asyncio.run(cli_research(query))
    elif len(sys.argv) > 1 and sys.argv[1] == "daily":
        from models.database import init_db
        from services.scheduler import run_daily_report

        async def _run() -> None:
            await init_db()
            await run_daily_report()

        asyncio.run(_run())
    else:
        main()
