from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, TYPE_CHECKING

from .handlers import ema_retest_v1, sfp_wickfade_v3
from .models import TradingViewPayload


@dataclass(frozen=True)
class StrategyConfig:
    default_venue: str
    default_timeframe: str
    default_risk_usd: float
    handler: Callable[["EvalManager", str, str, TradingViewPayload], int]


if TYPE_CHECKING:
    from .eval_manager import EvalManager


STRATEGY_REGISTRY: Dict[str, StrategyConfig] = {
    "sfp_wickfade_v3": StrategyConfig(
        default_venue="binance",
        default_timeframe="1h",
        default_risk_usd=50.0,
        handler=sfp_wickfade_v3,
    ),
    "ema_retest_v1": StrategyConfig(
        default_venue="bybit",
        default_timeframe="15m",
        default_risk_usd=25.0,
        handler=ema_retest_v1,
    ),
}


def default_handler(
    manager: "EvalManager",
    strategy_key: str,
    symbol: str,
    payload: TradingViewPayload,
) -> int:
    return manager.route_signal(strategy_key, symbol, payload)
