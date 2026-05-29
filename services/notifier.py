"""Telegram + Email notification helpers."""
from __future__ import annotations

import asyncio
from typing import Iterable, List, Optional

import httpx

from config import settings
from config.logging import logger
from models.schemas import ResearchReport


# Heuristic: any value containing one of these tokens is treated as a
# placeholder from .env.example and the notifier is skipped silently.
_PLACEHOLDER_HINTS = (
    "your_", "placeholder", "change_me", "example.com", "ABCDEF",
    "xxx", "1234567890:",
)


def _is_placeholder(value: Optional[str]) -> bool:
    if not value:
        return True
    v = value.strip().lower()
    return any(h.lower() in v for h in _PLACEHOLDER_HINTS)


class TelegramNotifier:
    """Async Telegram notifier."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.token = token or settings.telegram_token
        self.chat_id = chat_id or settings.telegram_chat_id

    @property
    def enabled(self) -> bool:
        return bool(
            self.token
            and self.chat_id
            and not _is_placeholder(self.token)
            and not _is_placeholder(self.chat_id)
        )

    async def send(self, text: str) -> bool:
        if not self.enabled:
            logger.debug("Telegram disabled - skipping")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text[:4000],
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(url, json=payload)
                if r.status_code != 200:
                    logger.warning("Telegram error {}: {}", r.status_code, r.text)
                    return False
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Telegram send failed: {}", e)
            return False


class EmailNotifier:
    """Async SMTP notifier (aiosmtplib)."""

    @property
    def enabled(self) -> bool:
        creds = (
            settings.smtp_host, settings.smtp_username, settings.smtp_password,
            settings.email_from, settings.email_to,
        )
        return bool(all(creds) and not any(_is_placeholder(c) for c in creds))

    async def send(self, subject: str, body: str) -> bool:
        if not self.enabled:
            logger.debug("Email disabled – skipping")
            return False
        try:
            import aiosmtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["From"] = settings.email_from
            msg["To"] = settings.email_to
            msg["Subject"] = subject
            msg.set_content(body)
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                start_tls=True,
                username=settings.smtp_username,
                password=settings.smtp_password,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Email send failed: {}", e)
            return False


def format_report_for_message(report: ResearchReport) -> str:
    lines = [
        f"*{report.title}*",
        f"标的: `{report.symbol}` ({report.market.value})",
        f"评级: *{report.recommendation}*  |  目标价: {report.target_price or '-'}  |  置信度: {report.confidence:.2f}",
        "",
        f"_摘要_: {report.executive_summary}",
    ]
    if report.fundamental:
        lines.append(f"\n*基本面*: {report.fundamental.summary[:600]}")
    if report.technical:
        lines.append(f"\n*技术面*: {report.technical.summary[:600]}")
    if report.risk:
        lines.append(f"\n*风险*: {report.risk.summary[:600]}")
    return "\n".join(lines)


async def broadcast_reports(reports: Iterable[ResearchReport]) -> None:
    tg = TelegramNotifier()
    em = EmailNotifier()
    for report in reports:
        text = format_report_for_message(report)
        await asyncio.gather(
            tg.send(text),
            em.send(report.title, text),
            return_exceptions=True,
        )
