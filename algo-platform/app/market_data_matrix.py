from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketDataMatrixRow:
    instrument_id: str
    display_name: str
    asset_class: str
    market: str
    exchange: str
    provider: str
    provider_type: str
    external_ticker: str
    stream_status: str
    cadence_target: str
    free_access: bool
    notes: str
    startup_enabled: bool = False


# This universe is intentionally crypto-only and maps to the top 100 OKX
# spot USDT markets by recent venue liquidity when this set was generated.
TOP_OKX_SPOT_PAIRS: tuple[str, ...] = (
    "BTC-USDT",
    "ETH-USDT",
    "BASED-USDT",
    "ORDI-USDT",
    "SOL-USDT",
    "DOGE-USDT",
    "USDC-USDT",
    "XRP-USDT",
    "PEPE-USDT",
    "IP-USDT",
    "USDG-USDT",
    "SATS-USDT",
    "PNUT-USDT",
    "OFC-USDT",
    "SUI-USDT",
    "ENJ-USDT",
    "TRX-USDT",
    "TRUMP-USDT",
    "ADA-USDT",
    "NEIRO-USDT",
    "XAUT-USDT",
    "CORE-USDT",
    "HYPE-USDT",
    "FIL-USDT",
    "PI-USDT",
    "OKB-USDT",
    "AAVE-USDT",
    "BNB-USDT",
    "LINK-USDT",
    "BIO-USDT",
    "LTC-USDT",
    "PENGU-USDT",
    "TON-USDT",
    "ZEC-USDT",
    "WLD-USDT",
    "AVAX-USDT",
    "MERL-USDT",
    "UNI-USDT",
    "DOT-USDT",
    "SPACE-USDT",
    "TRB-USDT",
    "DYDX-USDT",
    "TIA-USDT",
    "XPL-USDT",
    "CFX-USDT",
    "NEAR-USDT",
    "KSM-USDT",
    "PUMP-USDT",
    "APT-USDT",
    "MOODENG-USDT",
    "WLFI-USDT",
    "PEOPLE-USDT",
    "AR-USDT",
    "XLM-USDT",
    "SHIB-USDT",
    "METIS-USDT",
    "ARB-USDT",
    "CHZ-USDT",
    "LDO-USDT",
    "PAXG-USDT",
    "ZETA-USDT",
    "BONK-USDT",
    "ACT-USDT",
    "ONDO-USDT",
    "TURBO-USDT",
    "KAT-USDT",
    "BCH-USDT",
    "LIT-USDT",
    "WIF-USDT",
    "NIGHT-USDT",
    "CRV-USDT",
    "MON-USDT",
    "ETC-USDT",
    "ENA-USDT",
    "HMSTR-USDT",
    "BOME-USDT",
    "RENDER-USDT",
    "BERA-USDT",
    "ASTER-USDT",
    "OL-USDT",
    "OP-USDT",
    "STRK-USDT",
    "VIRTUAL-USDT",
    "W-USDT",
    "HBAR-USDT",
    "VINE-USDT",
    "DASH-USDT",
    "LUNA-USDT",
    "ICP-USDT",
    "WET-USDT",
    "LRC-USDT",
    "ROBO-USDT",
    "ETHFI-USDT",
    "FET-USDT",
    "BLUR-USDT",
    "CC-USDT",
    "ZAMA-USDT",
    "CFG-USDT",
    "MEME-USDT",
    "MMT-USDT",
)

CORE_MULTI_EXCHANGE_SYMBOLS: tuple[str, ...] = (
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "DOGE",
    "ADA",
    "AVAX",
    "LINK",
    "LTC",
    "BCH",
    "DOT",
    "TRX",
    "UNI",
    "ETC",
    "FIL",
    "AAVE",
    "NEAR",
    "ARB",
    "SHIB",
)


def _build_okx_top_pair_rows() -> list[MarketDataMatrixRow]:
    rows: list[MarketDataMatrixRow] = []
    for external_ticker in TOP_OKX_SPOT_PAIRS:
        base_symbol = external_ticker.removesuffix("-USDT")
        rows.append(
            MarketDataMatrixRow(
                instrument_id=base_symbol,
                display_name=external_ticker,
                asset_class="crypto",
                market="spot",
                exchange="OKX",
                provider="okx",
                provider_type="direct_exchange_ws",
                external_ticker=external_ticker,
                stream_status="live_now",
                cadence_target="sub-second",
                free_access=True,
                notes="Public OKX spot ticker stream. This crypto-only matrix tracks the configured top 100 USDT pairs.",
                startup_enabled=True,
            )
        )
    return rows


def _build_cross_venue_rows() -> list[MarketDataMatrixRow]:
    rows: list[MarketDataMatrixRow] = []
    for symbol in CORE_MULTI_EXCHANGE_SYMBOLS:
        bybit_linear_ticker = "1000SHIBUSDT" if symbol == "SHIB" else f"{symbol}USDT"
        binance_futures_ticker = "1000SHIBUSDT" if symbol == "SHIB" else f"{symbol}USDT"
        rows.extend(
            [
                MarketDataMatrixRow(
                    instrument_id=f"{symbol}_OKX_PERP",
                    display_name=f"{symbol} / OKX Perp",
                    asset_class="crypto",
                    market="perp",
                    exchange="OKX",
                    provider="okx",
                    provider_type="direct_exchange_ws",
                    external_ticker=f"{symbol}-USDT-SWAP",
                    stream_status="live_now",
                    cadence_target="sub-second",
                    free_access=True,
                    notes="Public OKX perpetual swap ticker stream.",
                    startup_enabled=True,
                ),
                MarketDataMatrixRow(
                    instrument_id=f"{symbol}_BYBIT_SPOT",
                    display_name=f"{symbol} / Bybit Spot",
                    asset_class="crypto",
                    market="spot",
                    exchange="Bybit",
                    provider="bybit_spot",
                    provider_type="direct_exchange_ws",
                    external_ticker=f"{symbol}USDT",
                    stream_status="live_now",
                    cadence_target="50ms snapshots",
                    free_access=True,
                    notes="Public Bybit spot ticker stream.",
                    startup_enabled=True,
                ),
                MarketDataMatrixRow(
                    instrument_id=f"{symbol}_BYBIT_PERP",
                    display_name=f"{symbol} / Bybit Perp",
                    asset_class="crypto",
                    market="perp",
                    exchange="Bybit",
                    provider="bybit_linear",
                    provider_type="direct_exchange_ws",
                    external_ticker=bybit_linear_ticker,
                    stream_status="live_now",
                    cadence_target="100ms deltas",
                    free_access=True,
                    notes="Public Bybit USDT perpetual ticker stream.",
                    startup_enabled=True,
                ),
                MarketDataMatrixRow(
                    instrument_id=f"{symbol}_BINANCE_SPOT",
                    display_name=f"{symbol} / Binance Spot",
                    asset_class="crypto",
                    market="spot",
                    exchange="Binance",
                    provider="binance_spot",
                    provider_type="direct_exchange_ws",
                    external_ticker=f"{symbol}USDT",
                    stream_status="live_now",
                    cadence_target="1000ms ticker",
                    free_access=True,
                    notes="Public Binance spot ticker stream via market-data-only endpoint.",
                    startup_enabled=True,
                ),
                MarketDataMatrixRow(
                    instrument_id=f"{symbol}_BINANCE_PERP",
                    display_name=f"{symbol} / Binance Perp",
                    asset_class="crypto",
                    market="perp",
                    exchange="Binance Futures",
                    provider="binance_futures",
                    provider_type="direct_exchange_ws",
                    external_ticker=binance_futures_ticker,
                    stream_status="live_now",
                    cadence_target="1000ms ticker",
                    free_access=True,
                    notes="Public Binance USDT perpetual ticker stream.",
                    startup_enabled=True,
                ),
            ]
        )
    return rows


MARKET_DATA_MATRIX: tuple[MarketDataMatrixRow, ...] = tuple(
    _build_okx_top_pair_rows() + _build_cross_venue_rows()
)

LIVE_MARKET_DATA_ROWS: tuple[MarketDataMatrixRow, ...] = MARKET_DATA_MATRIX
