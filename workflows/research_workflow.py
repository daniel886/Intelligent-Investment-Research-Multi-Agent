"""LangGraph multi-agent workflow orchestration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents import FundamentalAgent, RiskAgent, TechnicalAgent
from agents.base import BaseAgent
from config.logging import logger
from models.schemas import (
    AgentReport,
    Market,
    ResearchReport,
    ResearchRequest,
)
from workflows.symbol_resolver import resolve_symbols


class GraphState(TypedDict, total=False):
    request: ResearchRequest
    symbol: str
    fundamental: Optional[AgentReport]
    technical: Optional[AgentReport]
    risk: Optional[AgentReport]
    final: Optional[ResearchReport]
    error: Optional[str]


class ResearchWorkflow:
    """LangGraph orchestrator coordinating the three specialist agents."""

    def __init__(self) -> None:
        self.fundamental = FundamentalAgent()
        self.technical = TechnicalAgent()
        self.risk = RiskAgent()
        self.synth_llm = self.fundamental.llm  # reuse one LLM
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------
    def _build_graph(self):
        sg = StateGraph(GraphState)
        sg.add_node("fundamental", self._node_fundamental)
        sg.add_node("technical", self._node_technical)
        sg.add_node("risk", self._node_risk)
        sg.add_node("synthesize", self._node_synthesize)

        # Run all three in parallel by branching from a single entry node
        sg.add_node("start", self._node_start)
        sg.set_entry_point("start")
        sg.add_edge("start", "fundamental")
        sg.add_edge("start", "technical")
        sg.add_edge("start", "risk")
        sg.add_edge("fundamental", "synthesize")
        sg.add_edge("technical", "synthesize")
        sg.add_edge("risk", "synthesize")
        sg.add_edge("synthesize", END)
        return sg.compile()

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------
    async def _node_start(self, state: GraphState) -> GraphState:
        logger.info("[Workflow] start node for {}", state.get("symbol"))
        return state

    async def _run_agent_safe(self, agent: BaseAgent, symbol: str) -> AgentReport:
        try:
            return await agent.run(symbol)
        except Exception as e:  # noqa: BLE001
            logger.exception("Agent {} failed: {}", agent.name, e)
            return AgentReport(
                agent=agent.name,
                symbol=symbol,
                summary=f"{agent.name} 执行失败：{e}",
                findings=[],
                confidence=0.0,
            )

    async def _node_fundamental(self, state: GraphState) -> GraphState:
        report = await self._run_agent_safe(self.fundamental, state["symbol"])
        return {"fundamental": report}

    async def _node_technical(self, state: GraphState) -> GraphState:
        report = await self._run_agent_safe(self.technical, state["symbol"])
        return {"technical": report}

    async def _node_risk(self, state: GraphState) -> GraphState:
        report = await self._run_agent_safe(self.risk, state["symbol"])
        return {"risk": report}

    async def _node_synthesize(self, state: GraphState) -> GraphState:
        symbol = state["symbol"]
        request = state["request"]
        funda = state.get("fundamental")
        tech = state.get("technical")
        risk = state.get("risk")

        market = Market.UNKNOWN
        if funda and funda.raw.get("fundamental"):
            market_val = funda.raw["fundamental"].get("market")
            if market_val:
                try:
                    market = Market(market_val) if not isinstance(market_val, Market) else market_val
                except Exception:  # noqa: BLE001
                    market = Market.UNKNOWN

        # Build synthesis prompt for the LLM
        ctx = (
            f"=== 基本面 ===\n{funda.summary if funda else 'N/A'}\n\n"
            f"=== 技术面 ===\n{tech.summary if tech else 'N/A'}\n\n"
            f"=== 风险评估 ===\n{risk.summary if risk else 'N/A'}\n"
        )
        sys_prompt = (
            "你是一位首席投资官 (CIO)，请综合三个子智能体的输出，"
            "给出最终中文投资研究报告，包含：执行摘要、综合判断、明确的投资评级"
            "（买入/增持/持有/减持/卖出/观望）、目标价（若可估算）、关键风险与催化剂、"
            "以及综合 confidence (0-1)。"
            "如果 language=en-US，则同时输出英文版本，并把双语放在 'bilingual' 字段中。"
        )
        user = (
            f"标的: {symbol}\n"
            f"用户原始指令: {request.query}\n"
            f"语言: {request.language}\n\n"
            f"{ctx}\n\n"
            "请输出严格的纯文本报告（不要 JSON），最后一行用：\n"
            "EVAL: <评级> | TARGET: <目标价或 -> | CONFIDENCE: <0-1>"
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        try:
            resp = await self.synth_llm.ainvoke(
                [SystemMessage(content=sys_prompt), HumanMessage(content=user)]
            )
            text = (resp.content or "").strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("Synthesis LLM failed: {}", e)
            text = ""

        # Parse the EVAL line
        recommendation = "观望"
        target_price: Optional[float] = None
        confidence = 0.0
        for line in (text or "").splitlines()[::-1]:
            if "EVAL:" in line:
                try:
                    parts = [p.strip() for p in line.split("|")]
                    for p in parts:
                        if p.startswith("EVAL:"):
                            v = p.split(":", 1)[1].strip()
                            if v in {"买入", "增持", "持有", "减持", "卖出", "观望"}:
                                recommendation = v  # type: ignore
                        elif p.startswith("TARGET:"):
                            tv = p.split(":", 1)[1].strip()
                            try:
                                target_price = float(tv) if tv not in {"-", "N/A", ""} else None
                            except ValueError:
                                target_price = None
                        elif p.startswith("CONFIDENCE:"):
                            cv = p.split(":", 1)[1].strip()
                            try:
                                confidence = float(cv)
                            except ValueError:
                                confidence = 0.0
                except Exception:  # noqa: BLE001
                    pass
                break

        bilingual: Optional[Dict[str, str]] = None
        if request.language == "en-US" and text:
            try:
                en_resp = await self.synth_llm.ainvoke(
                    [
                        SystemMessage(
                            content="Translate the following Chinese investment report to professional English. Keep all numbers and the EVAL line."
                        ),
                        HumanMessage(content=text),
                    ]
                )
                bilingual = {"zh-CN": text, "en-US": (en_resp.content or "").strip()}
            except Exception:  # noqa: BLE001
                bilingual = {"zh-CN": text}

        title = f"{symbol} 投资研究报告 - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        executive_summary = (text.splitlines()[0] if text else "未能生成执行摘要").strip()[:500]

        report = ResearchReport(
            request=request,
            symbol=symbol,
            market=market,
            title=title,
            executive_summary=executive_summary or text[:240] or "无摘要",
            fundamental=funda,
            technical=tech,
            risk=risk,
            recommendation=recommendation,  # type: ignore
            target_price=target_price,
            confidence=max(0.0, min(1.0, confidence)),
            bilingual=bilingual,
        )
        return {"final": report}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def run_for_symbol(self, request: ResearchRequest, symbol: str) -> ResearchReport:
        state: GraphState = {"request": request, "symbol": symbol}
        result: GraphState = await self.graph.ainvoke(state)
        final = result.get("final")
        if not final:
            final = ResearchReport(
                request=request,
                symbol=symbol,
                title=f"{symbol} 报告生成失败",
                executive_summary="工作流未生成最终报告",
            )
        return final

    async def run(self, request: ResearchRequest) -> List[ResearchReport]:
        symbols = list(request.symbols or [])
        if not symbols:
            symbols = resolve_symbols(request.query)
        if not symbols:
            logger.warning("No symbols resolved from query: {}", request.query)
            return []

        logger.info("[Workflow] running for symbols: {}", symbols)
        tasks = [self.run_for_symbol(request, s) for s in symbols]
        return await asyncio.gather(*tasks)


# Singleton accessor
_workflow_singleton: Optional[ResearchWorkflow] = None


def get_workflow() -> ResearchWorkflow:
    global _workflow_singleton
    if _workflow_singleton is None:
        _workflow_singleton = ResearchWorkflow()
    return _workflow_singleton
