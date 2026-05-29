"""Base Agent — shared LLM access and prompt utilities."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import settings
from config.logging import logger
from models.schemas import AgentReport


# Round-2 fix #4: shared findings parser. Round-1 only fixed the CJK
# punctuation gap inside FundamentalAgent; TechnicalAgent (and any future
# agent) still relied on the old narrow `-/•/·` parser, which silently
# dropped Chinese-numbered findings (e.g. `1。`, `2、`). Centralising the
# parser here ensures every subclass stays in sync.
_BULLET_CHARS = ("-", "•", "·", "*", "—", "–")
# Latin: ).,  ;  CJK: 。、，；）：． ; full-width period
_NUMBERED_PUNCT = set(").,;:、。，；）：．")


def _parse_findings_lines(text: str, max_items: int) -> List[str]:
    findings: List[str] = []
    for line in (text or "").splitlines():
        l = line.strip()
        if not l:
            continue
        is_bullet = l.startswith(_BULLET_CHARS)
        is_numbered = (
            len(l) >= 2 and l[0].isdigit() and l[1] in _NUMBERED_PUNCT
        )
        # Two-digit ordinals (10. ...).
        if (
            not is_numbered
            and len(l) >= 3
            and l[0].isdigit()
            and l[1].isdigit()
            and l[2] in _NUMBERED_PUNCT
        ):
            is_numbered = True
        if not (is_bullet or is_numbered):
            continue
        cleaned = l.lstrip("-•·*—– ").strip()
        if is_numbered:
            i = 0
            while i < len(cleaned) and cleaned[i].isdigit():
                i += 1
            while i < len(cleaned) and cleaned[i] in _NUMBERED_PUNCT:
                i += 1
            cleaned = cleaned[i:].strip()
        if cleaned:
            findings.append(cleaned)
    return findings[:max_items]


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

    @staticmethod
    def parse_findings(text: str, max_items: int = 6) -> List[str]:
        """Extract bullet/numbered findings from an LLM summary.

        Recognises Latin and CJK punctuation so Chinese-numbered lists
        (e.g. ``1。``, ``2、``) match. Used by every subclass to keep parsing
        behaviour consistent.
        """
        return _parse_findings_lines(text, max_items)

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
