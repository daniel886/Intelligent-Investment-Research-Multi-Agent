"""Symbol resolution: extract tickers from natural-language Chinese/English prompts."""
from __future__ import annotations

import re
from typing import List

# Lightweight name → ticker dictionary for popular A股/港股/美股/加密货币
NAME_MAP = {
    # 美股 / US
    "苹果": "AAPL",
    "微软": "MSFT",
    "谷歌": "GOOGL",
    "亚马逊": "AMZN",
    "特斯拉": "TSLA",
    "英伟达": "NVDA",
    "脸书": "META",
    "meta": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "网飞": "NFLX",
    # 港股 / HK
    "腾讯": "0700.HK",
    "腾讯控股": "0700.HK",
    "阿里": "9988.HK",
    "阿里巴巴": "9988.HK",
    "美团": "3690.HK",
    "小米": "1810.HK",
    "比亚迪": "1211.HK",
    # A股
    "茅台": "600519.SS",
    "贵州茅台": "600519.SS",
    "宁德时代": "300750.SZ",
    "招商银行": "600036.SS",
    "平安银行": "000001.SZ",
    # 加密货币
    "比特币": "BTC-USD",
    "btc": "BTC-USD",
    "以太坊": "ETH-USD",
    "eth": "ETH-USD",
    "狗狗币": "DOGE-USD",
    "doge": "DOGE-USD",
}

TICKER_PATTERN = re.compile(
    r"\b("
    r"[A-Z]{1,6}(?:-USD|-USDT)?"   # US / Crypto
    r"|\d{5,6}\.(?:HK|SS|SZ)"      # HK / A股
    r"|0?\d{4,5}\.HK"
    r")\b",
    re.IGNORECASE,
)

# English stop-words / common nouns that look like tickers but aren't.
STOPWORDS = {
    "A", "I", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN", "IS", "IT",
    "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE", "AM", "PM",
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER", "WAS",
    "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW", "MAN", "NEW",
    "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "BOY", "DID", "MOM", "DAD",
    "MOON", "BEST", "GOOD", "BUY", "SELL", "HOLD", "NEWS", "LIKE", "LOVE",
    "TESLA", "APPLE", "GOOGLE", "META", "NETFLIX",  # Chinese-name companions
    "PRICE", "STOCK", "MARKET", "ANALYZE", "REPORT", "CHART",
    "BTC", "ETH", "USD", "USDT", "USDC", "RMB", "CNY", "HKD", "JPY",
    "OK", "YES", "NO", "WTF", "OMG", "LOL", "ASAP", "FYI", "AKA", "ETC",
    "API", "CEO", "CFO", "COO", "CTO", "GDP", "CPI", "PMI", "IPO", "ETF",
    "USA", "EU", "UK", "CN", "JP", "KR", "HK",
}


def _is_valid_ticker(token: str) -> bool:
    """Filter out obvious non-tickers."""
    t = token.upper().strip()
    if not t:
        return False
    if "." in t:                    # always keep .HK / .SS / .SZ
        return True
    if "-" in t:                    # crypto pairs (BTC-USD)
        return True
    if t in STOPWORDS:
        return False
    if len(t) < 2 or len(t) > 5:    # US tickers 2-5 chars
        return False
    return True


def resolve_symbols(text: str) -> List[str]:
    """Pull tickers + map Chinese names from a free-form instruction."""
    if not text:
        return []
    found: List[str] = []
    for m in TICKER_PATTERN.finditer(text):
        candidate = m.group(1).upper()
        if _is_valid_ticker(candidate):
            found.append(candidate)
    lowered = text.lower()
    for name, ticker in NAME_MAP.items():
        if name in lowered or name in text:
            found.append(ticker)
    # Deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for s in found:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique
