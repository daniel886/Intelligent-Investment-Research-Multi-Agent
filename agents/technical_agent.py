"""Technical analysis agent."""
from __future__ import annotations

from typing import Any

from config.logging import logger
from models.schemas import AgentReport
from tools.indicators import compute_indicators
from tools.polygon_tool import PolygonClient
from tools.yfinance_tool import YFinanceClient

from .base import BaseAgent


class TechnicalAgent(BaseAgent):
    name = "technical_agent"
    system_prompt = (
        "你是一名顶级量化技术分析师。基于提供的指标输出明确的中文交易信号，"
        "包含趋势判断、关键支撑/压力、动量、量能、入场/止损建议。要求结论可执行。"
    )

    def __init__(self) -> None:
        super().__init__()
        self.yf = YFinanceClient()
        self.polygon = PolygonClient()

    async def run(self, symbol: str, **kwargs: Any) -> AgentReport:
        logger.info("[Technical] analysing {}", symbol)
        bars = await self.yf.get_history(symbol, period="1y", interval="1d")
        if not bars:
            bars = await self.polygon.get_aggregates(symbol, days=240)
        snap = compute_indicators(symbol, bars)
        if not snap:
            return self._empty_report(symbol, reason="历史 K 线数据不足")

        context = (
            f"标的: {symbol}\n"
            f"最新价: {snap.last_price:.4f} ({(snap.change_pct or 0):+.2f}%)\n"
            f"SMA20/50/200: {snap.sma_20} / {snap.sma_50} / {snap.sma_200}\n"
            f"RSI14: {snap.rsi_14}\n"
            f"MACD: {snap.macd} (signal {snap.macd_signal})\n"
            f"布林带上下轨: {snap.bb_upper} / {snap.bb_lower}\n"
            f"近期信号: {snap.signals}\n"
            f"趋势: {snap.trend}"
        )

        prompt = (
            "请基于上述指标输出：\n"
            "1) 当前主趋势 (短/中/长期)；\n"
            "2) 关键支撑与压力位 (具体数值)；\n"
            "3) 动量与量能解读；\n"
            "4) 操作建议 (入场区间、止损、目标价)；\n"
            "5) 综合技术评分（0-100）。\n"
            "最后给出 3-5 条要点。"
        )
        summary = await self.llm_summary(prompt, context)

        # Round-2 fix #4 (agents/technical_agent.py:61): use the shared
        # parse_findings helper so CJK-numbered lists (`1。`, `2、`, …) match
        # — the previous narrow `-/•/·` parser silently dropped them.
        findings = list(snap.signals)
        findings.extend(self.parse_findings(summary, max_items=8))
        findings = list(dict.fromkeys(findings))[:8]

        return AgentReport(
            agent=self.name,
            symbol=symbol,
            summary=summary or "技术面分析失败。",
            findings=findings,
            confidence=0.7 if snap.sma_50 else 0.5,
            raw={"technical": self._safe_dict(snap), "bars_count": len(bars)},
        )
