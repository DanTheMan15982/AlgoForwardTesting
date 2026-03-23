from __future__ import annotations

from typing import TYPE_CHECKING

from .models import TradingViewPayload

if TYPE_CHECKING:
    from .eval_manager import EvalManager


def sfp_wickfade_v3(
    manager: "EvalManager",
    strategy_key: str,
    symbol: str,
    payload: TradingViewPayload,
) -> int:
    print("handler: sfp_wickfade_v3")
    return manager.route_signal(strategy_key, symbol, payload)


def ema_retest_v1(
    manager: "EvalManager",
    strategy_key: str,
    symbol: str,
    payload: TradingViewPayload,
) -> int:
    print("handler: ema_retest_v1")
    return manager.route_signal(strategy_key, symbol, payload)
