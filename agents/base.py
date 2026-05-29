"""Base Agent — shared LLM access and prompt utilities."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import settings
from config.logging import logger
from models.schemas import AgentReport


class BaseAgent(ABC):
    """All specialised agents extend this class."""

    name: str = "base"
    system_prompt: str = "You are a helpful financial AI agent."

    def __init__(self, llm: Optional[ChatOpenAI] = None) -> None:
        self.llm = llm or self._default_llm()

    @staticmethod
    def _default_llm() -> ChatOpenAI:
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.2,
            timeout=60,
            max_retries=2,
        )

    async def llm_summary(self, prompt: str, context: str = "") -> str:
        """Helper – run the LLM with the agent's system prompt."""
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"{context}\n\n{prompt}".strip()),
        ]
        try:
            resp = await self.llm.ainvoke(messages)
            return (resp.content or "").strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM call failed for {}: {}", self.name, e)
            return ""

    @abstractmethod
    async def run(self, symbol: str, **kwargs: Any) -> AgentReport:
        """Execute analysis for a single symbol."""
        raise NotImplementedError

    def _empty_report(self, symbol: str, reason: str = "") -> AgentReport:
        return AgentReport(
            agent=self.name,
            symbol=symbol,
            summary=f"{self.name} 未能产出报告。原因：{reason}" if reason else f"{self.name} 数据不足。",
            findings=[],
            confidence=0.0,
            raw={},
        )

    @staticmethod
    def _safe_dict(obj: Any) -> Dict[str, Any]:
        try:
            return obj.model_dump() if hasattr(obj, "model_dump") else dict(obj)
        except Exception:  # noqa: BLE001
            return {}
