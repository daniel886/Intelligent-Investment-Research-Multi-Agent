"""Risk assessment agent."""
from __future__ import annotations

from typing import Any

from config.logging import logger
from models.schemas import AgentReport, RiskAssessment, RiskLevel
from tools.indicators import compute_risk_metrics
from tools.yfinance_tool import YFinanceClient

from .base import BaseAgent


class RiskAgent(BaseAgent):
    name = "risk_agent"
    system_prompt = (
        "你是一名专业的投资风险分析师。基于波动率、最大回撤、Beta、VaR 等指标，"
        "结合宏观、行业、公司治理风险，输出严谨的中文风险评估报告。"
    )

    def __init__(self) -> None:
        super().__init__()
        self.yf = YFinanceClient()

    @staticmethod
    def _classify(volatility: float | None, drawdown: float | None) -> RiskLevel:
        v = volatility or 0
        dd = abs(drawdown or 0)
        score = v * 0.5 + dd * 0.5
        if score < 25:
            return RiskLevel.LOW
        if score < 45:
            return RiskLevel.MEDIUM
        if score < 70:
            return RiskLevel.HIGH
        return RiskLevel.EXTREME

    async def run(self, symbol: str, **kwargs: Any) -> AgentReport:
        logger.info("[Risk] analysing {}", symbol)
        bars = await self.yf.get_history(symbol, period="1y", interval="1d")
        if not bars:
            return self._empty_report(symbol, reason="无法获取历史价格")

        volatility, max_dd, var_95 = compute_risk_metrics(bars)
        if volatility is None or max_dd is None or var_95 is None:
            # compute_risk_metrics needs at least ~20 bars; bail out gracefully
            # instead of crashing on the f-string below.
            return self._empty_report(
                symbol,
                reason=f"历史数据不足（仅 {len(bars)} 条 K 线，至少需要 20 条）",
            )
        level = self._classify(volatility, max_dd)
        risk = RiskAssessment(
            symbol=symbol,
            risk_level=level,
            volatility=volatility,
            max_drawdown=max_dd,
            var_95=var_95,
            beta=None,
        )

        context = (
            f"标的: {symbol}\n"
            f"年化波动率: {volatility:.2f}% \n"
            f"近一年最大回撤: {max_dd:.2f}% \n"
            f"日 95% VaR: {var_95:.2f}% \n"
            f"分级: {level.value}\n"
        )
        prompt = (
            "请基于上述统计与一般市场知识，给出：\n"
            "1) 主要风险点（流动性、估值、财务、合规、地缘、行业等）；\n"
            "2) 潜在机会点；\n"
            "3) 风险应对建议（仓位、止损、对冲）；\n"
            "4) 综合风险评分（0-100，越高越危险）。\n"
            "最后输出 3-5 条要点。"
        )
        summary = await self.llm_summary(prompt, context)
        findings = []
        for line in (summary or "").splitlines():
            l = line.strip()
            if l.startswith(("-", "•", "·")):
                findings.append(l.lstrip("-•· ").strip())
        findings = findings[:6]

        return AgentReport(
            agent=self.name,
            symbol=symbol,
            summary=summary or "风险评估失败。",
            findings=findings,
            confidence=0.65,
            raw={"risk": self._safe_dict(risk)},
        )
