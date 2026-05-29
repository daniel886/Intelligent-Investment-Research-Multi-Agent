"""Fundamental analysis agent."""
from __future__ import annotations

from typing import Any

from config.logging import logger
from models.schemas import AgentReport, FundamentalSnapshot
from tools.alpha_vantage_tool import AlphaVantageClient
from tools.news_tool import NewsAggregator
from tools.yfinance_tool import YFinanceClient

from .base import BaseAgent


class FundamentalAgent(BaseAgent):
    name = "fundamental_agent"
    system_prompt = (
        "你是一名资深基本面分析师，擅长解读财报、行业地位、商业模式和估值水平。"
        "请基于给定数据用中文给出严谨、可执行、明确的结论，"
        "避免空话，关键论点务必引用具体数字。"
    )

    def __init__(self) -> None:
        super().__init__()
        self.yf = YFinanceClient()
        self.av = AlphaVantageClient()
        self.news = NewsAggregator()

    async def run(self, symbol: str, **kwargs: Any) -> AgentReport:
        logger.info("[Fundamental] analysing {}", symbol)
        snapshot: FundamentalSnapshot = await self.yf.get_fundamentals(symbol)
        overview = await self.av.get_company_overview(symbol)
        news = await self.news.fetch_all(symbol, limit=8)

        context_lines = [
            f"标的: {symbol} ({snapshot.name or 'N/A'})",
            f"市场: {snapshot.market.value}",
            f"行业: {snapshot.industry or overview.get('Industry') or 'N/A'}",
            f"市值: {snapshot.market_cap}",
            f"PE: {snapshot.pe_ratio} | PB: {snapshot.pb_ratio} | EPS: {snapshot.eps}",
            f"营收: {snapshot.revenue}, 营收增速: {snapshot.revenue_growth}",
            f"净利率: {snapshot.profit_margin}, ROE: {snapshot.roe}, D/E: {snapshot.debt_to_equity}",
            f"股息率: {snapshot.dividend_yield}",
            f"业务简介: {(snapshot.summary or overview.get('Description') or '')[:500]}",
        ]
        if news:
            context_lines.append("近期新闻:")
            for n in news[:6]:
                context_lines.append(f"- {n.title} ({n.source or 'N/A'})")
        context = "\n".join(context_lines)

        prompt = (
            "请基于以上信息，从以下角度给出基本面分析：\n"
            "1) 公司业务质量与护城河；\n"
            "2) 财务健康度（盈利、增长、现金流、负债）；\n"
            "3) 估值合理性（与历史和行业平均比较）；\n"
            "4) 关键基本面催化剂与风险点；\n"
            "5) 综合基本面评分（0-100）。\n"
            "最后给出 3-5 条要点 (findings)，每条 1 行。"
        )
        summary = await self.llm_summary(prompt, context)

        # Parse findings: take last 5 non-empty lines starting with - or 数字
        findings = []
        for line in (summary or "").splitlines():
            l = line.strip()
            if not l:
                continue
            if l.startswith(("-", "•", "·")) or (len(l) > 2 and l[0].isdigit() and l[1] in ").、,"):
                findings.append(l.lstrip("-•· ").strip())
        findings = findings[:6]

        confidence = 0.6
        if snapshot.pe_ratio and snapshot.market_cap:
            confidence = 0.8

        return AgentReport(
            agent=self.name,
            symbol=symbol,
            summary=summary or "数据不足，未能完成基本面分析。",
            findings=findings,
            confidence=confidence,
            raw={
                "fundamental": self._safe_dict(snapshot),
                "alpha_vantage_overview": overview or {},
                "news_count": len(news),
            },
        )
