"""Smoke tests – no external network calls."""
from __future__ import annotations

import pytest

from models.schemas import (
    AgentReport,
    Market,
    ResearchReport,
    ResearchRequest,
    RiskLevel,
)
from workflows.symbol_resolver import resolve_symbols


def test_resolve_symbols_chinese():
    s = resolve_symbols("请分析腾讯控股 和 比特币 还有 AAPL")
    assert "0700.HK" in s
    assert "BTC-USD" in s
    assert "AAPL" in s


def test_resolve_symbols_a_share():
    s = resolve_symbols("看一下 600519.SS 茅台")
    assert "600519.SS" in s


def test_research_report_serialization():
    req = ResearchRequest(query="test", language="zh-CN")
    rep = ResearchReport(
        request=req,
        symbol="AAPL",
        market=Market.US,
        title="t",
        executive_summary="s",
    )
    d = rep.model_dump()
    assert d["symbol"] == "AAPL"
    assert d["recommendation"] == "观望"


def test_risk_levels_enum():
    assert RiskLevel.LOW.value == "low"
    assert RiskLevel.EXTREME.value == "extreme"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("分析特斯拉", "TSLA"),
        ("买入英伟达", "NVDA"),
        ("eth 走势", "ETH-USD"),
    ],
)
def test_named_resolution(text, expected):
    assert expected in resolve_symbols(text)
