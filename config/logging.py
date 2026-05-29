"""Centralised logging using Loguru."""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from config import settings


_CONFIGURED = False


def setup_logging() -> None:
    """Configure global Loguru logger. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = Path(settings.project_root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
            "| <level>{level: <8}</level> "
            "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "- <level>{message}</level>"
        ),
        backtrace=True,
        diagnose=False,
        enqueue=True,
    )
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="14 days",
        level=settings.log_level,
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
    _CONFIGURED = True


__all__ = ["logger", "setup_logging"]
