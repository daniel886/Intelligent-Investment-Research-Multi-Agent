"""Pydantic v2 schemas shared across agents and API."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


# ============================================================
#                        Enums
# ============================================================
class Market(str, Enum):
    A_SHARE = "A股"
    HK = "港股"
    US = "美股"
    CRYPTO = "加密货币"
    UNKNOWN = "未知"


class Sentiment(str, Enum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


# ============================================================
#                  Generic data containers
# ============================================================
class PriceBar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class NewsItem(BaseModel):
    title: str
    url: Optional[str] = None
    source: Optional[str] = None
    published_at: Optional[datetime] = None
    summary: Optional[str] = None
    sentiment: Optional[Sentiment] = None


class FundamentalSnapshot(BaseModel):
    symbol: str
    name: Optional[str] = None
    market: Market = Market.UNKNOWN
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    eps: Optional[float] = None
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_income: Optional[float] = None
    profit_margin: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None
    dividend_yield: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    summary: Optional[str] = None


class TechnicalSnapshot(BaseModel):
    symbol: str
    last_price: float
    change_pct: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    volume_avg: Optional[float] = None
    trend: Optional[Literal["up", "down", "sideways"]] = None
    signals: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    symbol: str
    risk_level: RiskLevel = RiskLevel.MEDIUM
    volatility: Optional[float] = None
    max_drawdown: Optional[float] = None
    beta: Optional[float] = None
    var_95: Optional[float] = None
    concerns: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)


# ============================================================
#                  Agent + Workflow IO
# ============================================================
class AgentReport(BaseModel):
    agent: str
    symbol: str
    summary: str
    findings: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    raw: Dict[str, Any] = Field(default_factory=dict)


class ResearchRequest(BaseModel):
    """User-facing research request."""

    query: str = Field(..., description="Natural-language instruction (中文/EN)")
    symbols: Optional[List[str]] = Field(default=None, description="Optional list of tickers")
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    deep: bool = Field(default=False, description="Whether to run deep research")


class ResearchReport(BaseModel):
    """Final assembled investment research report."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[int] = None
    request: ResearchRequest
    symbol: str
    market: Market = Market.UNKNOWN
    title: str
    executive_summary: str
    fundamental: Optional[AgentReport] = None
    technical: Optional[AgentReport] = None
    risk: Optional[AgentReport] = None
    recommendation: Literal["买入", "增持", "持有", "减持", "卖出", "观望"] = "观望"
    target_price: Optional[float] = None
    confidence: float = 0.0
    bilingual: Optional[Dict[str, str]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DailyDigest(BaseModel):
    date: datetime
    summary: str
    reports: List[ResearchReport] = Field(default_factory=list)
