from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional
import hashlib
import json

from .db import EvalRow, PositionRow


@dataclass(frozen=True)
class RollingStats:
    count: int
    wins: int
    losses: int
    breakeven: int
    net_pnl: float
    avg_pnl: Optional[float]
    win_rate: Optional[float]
    profit_factor: Optional[float]
    avg_win: Optional[float]
    avg_loss: Optional[float]
    loss_rate: Optional[float]
    avg_loss_trade: Optional[float]
    oldest_closed_at: Optional[datetime]
    newest_closed_at: Optional[datetime]


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _profit_factor(gross_profit: float, gross_loss: float) -> Optional[float]:
    if gross_loss <= 0:
        return None
    return gross_profit / gross_loss


def compute_totals(positions: Iterable[PositionRow]) -> dict[str, Optional[float]]:
    wins = losses = breakeven = 0
    gross_profit = 0.0
    gross_loss = 0.0
    for pos in positions:
        if pos.pnl is None:
            continue
        if pos.pnl > 0:
            wins += 1
            gross_profit += pos.pnl
        elif pos.pnl < 0:
            losses += 1
            gross_loss += abs(pos.pnl)
        else:
            breakeven += 1
    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades else None
    avg_win = (gross_profit / wins) if wins else None
    avg_loss = (gross_loss / losses) if losses else None
    return {
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "win_rate_pct": win_rate,
        "profit_factor": _profit_factor(gross_profit, gross_loss),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def compute_rr_metrics(positions: Iterable[PositionRow]) -> dict[str, Optional[float]]:
    values = [pos.r_multiple for pos in positions if pos.r_multiple is not None]
    n_valid = len(values)
    wins = [value for value in values if value > 0]
    n_wins = len(wins)
    avg_win_r = (sum(wins) / n_wins) if n_wins else None
    expectancy_r = (sum(values) / n_valid) if n_valid else None
    win_rate_r = (n_wins / n_valid * 100) if n_valid else None
    return {
        "avg_win_r": avg_win_r,
        "expectancy_r": expectancy_r,
        "win_rate_r": win_rate_r,
        "n_valid_r": n_valid,
        "n_wins_r": n_wins,
    }


def compute_rolling(positions: list[PositionRow]) -> RollingStats:
    wins = losses = breakeven = 0
    net_pnl = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    loss_values = []
    for pos in positions:
        pnl = pos.pnl or 0.0
        net_pnl += pnl
        if pnl > 0:
            wins += 1
            gross_profit += pnl
        elif pnl < 0:
            losses += 1
            gross_loss += abs(pnl)
            loss_values.append(abs(pnl))
        else:
            breakeven += 1
    count = len(positions)
    avg_pnl = (net_pnl / count) if count else None
    total_wl = wins + losses
    win_rate = (wins / total_wl) if total_wl else None
    avg_win = (gross_profit / wins) if wins else None
    avg_loss = (gross_loss / losses) if losses else None
    loss_rate = (losses / count) if count else None
    avg_loss_trade = (sum(loss_values) / len(loss_values)) if loss_values else None
    oldest = _parse_ts(positions[-1].closed_at) if positions else None
    newest = _parse_ts(positions[0].closed_at) if positions else None
    return RollingStats(
        count=count,
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        net_pnl=net_pnl,
        avg_pnl=avg_pnl,
        win_rate=win_rate,
        profit_factor=_profit_factor(gross_profit, gross_loss),
        avg_win=avg_win,
        avg_loss=avg_loss,
        loss_rate=loss_rate,
        avg_loss_trade=avg_loss_trade,
        oldest_closed_at=oldest,
        newest_closed_at=newest,
    )


def compute_profit_target(row: EvalRow) -> dict[str, Optional[float]]:
    pct = normalize_profit_target_pct(row.profit_target_pct)
    if pct is None:
        return {
            "profit_target_equity": None,
            "profit_remaining_usd": None,
            "profit_progress_pct": None,
        }
    target = row.starting_balance * (1 + pct)
    remaining = max(0.0, target - row.current_equity)
    denom = target - row.starting_balance
    progress = ((row.current_equity - row.starting_balance) / denom) if denom != 0 else None
    if progress is not None:
        progress = min(1.0, max(0.0, progress))
    return {
        "profit_target_equity": target,
        "profit_remaining_usd": remaining,
        "profit_progress_pct": progress,
    }


def normalize_profit_target_pct(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if value > 1:
        return value / 100
    return value


def compute_etas(row: EvalRow, rolling: RollingStats) -> dict[str, Optional[float]]:
    if rolling.count < 5:
        return {
            "expected_trades_to_pass": None,
            "expected_days_to_pass": None,
            "expected_trades_to_daily_fail": None,
            "expected_trades_to_max_fail": None,
        }

    profit_fields = compute_profit_target(row)
    profit_remaining = profit_fields["profit_remaining_usd"]
    expected_trades_to_pass = None
    expected_days_to_pass = None
    if profit_remaining is not None and rolling.avg_pnl and rolling.avg_pnl > 0:
        expected_trades_to_pass = profit_remaining / rolling.avg_pnl
        if rolling.oldest_closed_at and rolling.newest_closed_at:
            delta = (rolling.newest_closed_at - rolling.oldest_closed_at).total_seconds()
            days = max(1.0, delta / 86400.0)
            trades_per_day = rolling.count / days
            if trades_per_day > 0:
                expected_days_to_pass = expected_trades_to_pass / trades_per_day

    max_floor = row.starting_balance * (1 - row.max_dd_pct)
    daily_floor = row.day_start_equity * (1 - row.daily_dd_pct)
    max_remaining = row.current_equity - max_floor
    daily_remaining = row.current_equity - daily_floor
    expected_loss_per_trade = None
    if rolling.loss_rate and rolling.avg_loss_trade:
        expected_loss_per_trade = rolling.loss_rate * rolling.avg_loss_trade

    expected_trades_to_daily_fail = None
    expected_trades_to_max_fail = None
    if expected_loss_per_trade and expected_loss_per_trade > 0:
        expected_trades_to_daily_fail = max(0.0, daily_remaining / expected_loss_per_trade)
        expected_trades_to_max_fail = max(0.0, max_remaining / expected_loss_per_trade)

    return {
        "expected_trades_to_pass": expected_trades_to_pass,
        "expected_days_to_pass": expected_days_to_pass,
        "expected_trades_to_daily_fail": expected_trades_to_daily_fail,
        "expected_trades_to_max_fail": expected_trades_to_max_fail,
    }


def summarize_eval(
    row: EvalRow,
    closed_positions: list[PositionRow],
    rolling_positions: list[PositionRow],
) -> dict[str, Optional[float]]:
    totals = compute_totals(closed_positions)
    rr_metrics = compute_rr_metrics(closed_positions)
    rolling = compute_rolling(rolling_positions)
    profit_fields = compute_profit_target(row)
    etas = compute_etas(row, rolling)
    return {
        **totals,
        **rr_metrics,
        **profit_fields,
        "rolling_net_pnl": rolling.net_pnl if rolling.count else None,
        "rolling_avg_pnl_per_trade": rolling.avg_pnl if rolling.count else None,
        "rolling_win_rate": (rolling.win_rate * 100) if rolling.win_rate is not None else None,
        "rolling_profit_factor": rolling.profit_factor,
        "rolling_avg_win": rolling.avg_win,
        "rolling_avg_loss": rolling.avg_loss,
        **etas,
    }


def _calculate_rr(entry: float, stop: float, tp: Optional[float]) -> Optional[float]:
    if tp is None:
        return None
    risk = abs(entry - stop)
    reward = abs(tp - entry)
    if risk == 0:
        return None
    return reward / risk


def derive_strategy_family(strategy_key: str) -> tuple[str, Optional[str]]:
    if "_v" in strategy_key:
        base, _, version = strategy_key.rpartition("_v")
        if base:
            return base, f"v{version}"
    return strategy_key, None


def build_ruleset(row: EvalRow) -> dict[str, object]:
    return {
        "max_dd_pct": row.max_dd_pct,
        "daily_dd_pct": row.daily_dd_pct,
        "risk_usd": row.risk_usd,
        "fees_enabled": bool(row.fees_enabled),
        "slippage_enabled": bool(row.slippage_enabled),
        "taker_fee_rate": row.taker_fee_rate,
        "slippage_min_usd": row.slippage_min_usd,
        "slippage_max_usd": row.slippage_max_usd,
        "profit_target_pct": row.profit_target_pct,
        "latency_enabled": bool(row.latency_enabled),
        "latency_min_sec": row.latency_min_sec,
        "latency_max_sec": row.latency_max_sec,
    }


def ruleset_hash(ruleset: dict[str, object]) -> str:
    normalized = json.dumps(ruleset, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
