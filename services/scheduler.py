"""APScheduler-driven daily report job."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from config.logging import logger
from models.schemas import ResearchReport, ResearchRequest
from services.notifier import TelegramNotifier, broadcast_reports
from services.repository import ReportRepository, WatchlistRepository
from services.storage_cleaner import run_cleanup_cycle_async, sweep_trash
from workflows.research_workflow import get_workflow


_scheduler: Optional[AsyncIOScheduler] = None


async def run_daily_report(symbols: Optional[List[str]] = None) -> List[ResearchReport]:
    """Run analysis for watchlist + send notification."""
    if symbols is None:
        watch = await WatchlistRepository.list_all()
        symbols = [w.symbol for w in watch] or settings.watchlist_symbols
    if not symbols:
        logger.warning("Daily report skipped — empty watchlist")
        return []

    logger.info("[Scheduler] running daily report for {}", symbols)
    request = ResearchRequest(
        query=f"生成每日投资日报 ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})",
        symbols=symbols,
        language=settings.language,
    )
    workflow = get_workflow()
    reports = await workflow.run(request)
    for r in reports:
        try:
            await ReportRepository.save(r)
        except Exception as e:  # noqa: BLE001
            logger.warning("Save report failed: {}", e)
    if reports:
        digest_lines = [
            f"📊 *每日投资日报* {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"覆盖标的: {', '.join(symbols)}",
            "",
        ]
        for r in reports:
            digest_lines.append(
                f"• `{r.symbol}` — *{r.recommendation}* (置信度 {r.confidence:.2f})"
            )
        digest = "\n".join(digest_lines)
        await TelegramNotifier().send(digest)
        await broadcast_reports(reports)
    return reports


def init_scheduler() -> AsyncIOScheduler:
    """Boot APScheduler with the daily-report cron trigger."""
    global _scheduler
    if _scheduler:
        return _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    try:
        trigger = CronTrigger.from_crontab(settings.daily_report_cron)
    except Exception as e:  # noqa: BLE001
        logger.warning("Invalid DAILY_REPORT_CRON='{}', fallback 0 9 * * 1-5: {}", settings.daily_report_cron, e)
        trigger = CronTrigger.from_crontab("0 9 * * 1-5")
    _scheduler.add_job(
        run_daily_report,
        trigger=trigger,
        id="daily_report",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # ---- Storage cleanup job (non-blocking, permission-tolerant) ----
    if getattr(settings, "cleanup_enabled", True):
        try:
            cleanup_trigger = CronTrigger.from_crontab(settings.cleanup_cron)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Invalid CLEANUP_CRON='{}', fallback '30 3 * * *': {}",
                getattr(settings, "cleanup_cron", "?"), e,
            )
            cleanup_trigger = CronTrigger.from_crontab("30 3 * * *")
        _scheduler.add_job(
            run_cleanup_cycle_async,
            trigger=cleanup_trigger,
            id="storage_cleanup",
            replace_existing=True,
            misfire_grace_time=900,
        )
        # Opportunistic startup sweep — never raises, bounded to ~2s.
        try:
            swept = sweep_trash(max_seconds=2.0)
            if swept:
                logger.info("storage_cleaner: startup sweep removed {} entries", swept)
        except Exception as e:  # noqa: BLE001
            logger.debug("storage_cleaner: startup sweep skipped ({})", e)

    _scheduler.start()
    logger.info(
        "APScheduler started (report='{}', cleanup='{}')",
        settings.daily_report_cron,
        getattr(settings, "cleanup_cron", "disabled"),
    )
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


if __name__ == "__main__":
    # Allow running scheduler standalone (separate worker container)
    asyncio.run(run_daily_report())
