from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, Optional, Tuple
from zoneinfo import ZoneInfo

from .models import Side, TradingViewPayload

ET_TZ = ZoneInfo("America/New_York")


def _format_validation_errors(errors: Iterable[str]) -> str:
    return "Invalid payload: " + "; ".join(errors)


def validate_payload(payload: TradingViewPayload, require_tp: bool = False) -> None:
    errors = []
    if payload.stop is None:
        errors.append("stop: field required")
    if require_tp and payload.tp is None:
        errors.append("tp: field required")

    if errors:
        raise ValueError(_format_validation_errors(errors))


def map_ticker_to_symbol(ticker: str) -> Optional[str]:
    upper = ticker.upper()
    if upper.startswith("BTC"):
        return "BTC"
    if upper.startswith("ETH"):
        return "ETH"
    if upper.startswith("SOL"):
        return "SOL"
    return None


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def et_day_key(now: datetime) -> str:
    aware = ensure_aware(now)
    return aware.astimezone(ET_TZ).date().isoformat()


def et_midnight_for_day_key(day_key: str) -> datetime:
    day = date.fromisoformat(day_key)
    return datetime.combine(day, time.min, tzinfo=ET_TZ)


def next_et_midnight(now: datetime) -> datetime:
    aware = ensure_aware(now)
    now_et = aware.astimezone(ET_TZ)
    next_day = now_et.date() + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=ET_TZ)


def compute_r_multiple(
    side: str,
    entry_price: Optional[float],
    stop_price: Optional[float],
    exit_price: Optional[float],
) -> Optional[Decimal]:
    if entry_price is None or stop_price is None or exit_price is None:
        return None
    try:
        entry = Decimal(str(entry_price))
        stop = Decimal(str(stop_price))
        exit_val = Decimal(str(exit_price))
    except (InvalidOperation, ValueError):
        return None
    risk = (entry - stop).copy_abs()
    if risk <= 0:
        return None
    if side == Side.LONG.value:
        reward = exit_val - entry
    elif side == Side.SHORT.value:
        reward = entry - exit_val
    else:
        return None
    r_multiple = reward / risk
    return r_multiple.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def evaluate_crossing(
    side: Side,
    stop_price: float,
    tp_price: Optional[float],
    bar_high: float,
    bar_low: float,
) -> Tuple[bool, bool]:
    if side == Side.LONG:
        tp_hit = tp_price is not None and bar_high >= tp_price
        stop_hit = bar_low <= stop_price
    else:
        tp_hit = tp_price is not None and bar_low <= tp_price
        stop_hit = bar_high >= stop_price
    return stop_hit, tp_hit
