from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .market_data_matrix import MARKET_DATA_MATRIX, MarketDataMatrixRow


INSTRUMENTS_BY_ID: dict[str, MarketDataMatrixRow] = {
    row.instrument_id: row for row in MARKET_DATA_MATRIX
}


def is_supported_instrument(symbol: str) -> bool:
    return symbol in INSTRUMENTS_BY_ID


def get_instrument(symbol: str) -> Optional[MarketDataMatrixRow]:
    return INSTRUMENTS_BY_ID.get(symbol)


def tradingview_ticker_for_symbol(symbol: str) -> str:
    row = get_instrument(symbol)
    if row is None:
        return symbol
    normalized = row.external_ticker.replace("-", "")
    if row.market == "perp":
        normalized = normalized.removesuffix("SWAP")
        return f"{normalized}.P"
    if normalized.endswith("USDT"):
        return normalized[:-4] + "USD"
    return normalized


@lru_cache(maxsize=1024)
def resolve_instrument_from_ticker(ticker: str) -> Optional[str]:
    normalized = ticker.strip().upper().replace(":", "")
    if not normalized:
        return None
    for symbol in INSTRUMENTS_BY_ID:
        if matches_instrument_ticker(symbol, normalized):
            return symbol
    return None


def matches_instrument_ticker(symbol: str, ticker: str) -> bool:
    row = get_instrument(symbol)
    if row is None:
        return False
    normalized = ticker.strip().upper().replace(":", "")
    if not normalized:
        return False

    aliases = {
        tradingview_ticker_for_symbol(symbol),
        row.external_ticker.upper(),
        row.external_ticker.replace("-", "").upper(),
    }
    if row.market == "spot":
        condensed = row.external_ticker.replace("-", "").upper()
        if condensed.endswith("USDT"):
            aliases.add(condensed)
            aliases.add(condensed[:-4] + "USD")
    if row.market == "perp":
        condensed = row.external_ticker.replace("-", "").upper().removesuffix("SWAP")
        aliases.add(condensed)
        aliases.add(f"{condensed}.P")
        if condensed.endswith("USDT"):
            aliases.add(condensed[:-4] + "USD.P")
    return normalized in aliases
