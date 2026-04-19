from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Optional


@dataclass(frozen=True)
class Trade:
    trade_no: int
    exit_ts: datetime
    side: str
    pnl_usd: float
    pnl_pct: float


def parse_tradingview_csv(content: bytes) -> list[Trade]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    trades: list[Trade] = []
    for row in reader:
        row_type = (row.get("Type") or "").strip().lower()
        if not row_type.startswith("exit"):
            continue
        try:
            trade_no = int(float((row.get("Trade #") or "0").strip()))
            exit_ts = datetime.strptime((row.get("Date and time") or "").strip(), "%Y-%m-%d %H:%M")
            pnl_usd = float((row.get("Net P&L USDT") or "0").replace(",", "").strip())
            pnl_pct = float((row.get("Net P&L %") or "0").replace(",", "").strip())
        except (ValueError, TypeError):
            continue
        side = "LONG" if "long" in row_type else "SHORT"
        trades.append(
            Trade(
                trade_no=trade_no,
                exit_ts=exit_ts,
                side=side,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
            )
        )
    trades.sort(key=lambda item: item.exit_ts)
    return trades


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak <= 0:
            continue
        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)
    return max_dd


def _simulate_path(
    pnl_sequence: list[float],
    date_sequence: list[datetime],
    starting_balance: float,
    max_dd_pct: float,
    daily_dd_pct: float,
    profit_target_pct: float,
) -> dict:
    equity = starting_balance
    max_floor = starting_balance * (1 - max_dd_pct)
    target = starting_balance * (1 + profit_target_pct)
    day_anchor = starting_balance
    current_day: Optional[str] = None
    equity_curve = [starting_balance]
    result = "OPEN"
    resolved_trade = None

    for idx, (pnl, ts) in enumerate(zip(pnl_sequence, date_sequence)):
        day_key = ts.date().isoformat()
        if current_day is None or day_key != current_day:
            current_day = day_key
            day_anchor = equity
        equity += pnl
        equity_curve.append(equity)
        daily_floor = day_anchor * (1 - daily_dd_pct)
        if equity <= max_floor:
            result = "FAIL_MAX_DD"
            resolved_trade = idx + 1
            break
        if equity <= daily_floor:
            result = "FAIL_DAILY_DD"
            resolved_trade = idx + 1
            break
        if equity >= target:
            result = "PASS_TARGET"
            resolved_trade = idx + 1
            break

    return {
        "result": result,
        "resolved_trade_count": resolved_trade,
        "final_equity": equity_curve[-1],
        "max_drawdown_pct": _max_drawdown_pct(equity_curve),
        "equity_curve": equity_curve,
    }


def analyze_backtest(
    trades: list[Trade],
    *,
    starting_balance: float,
    max_dd_pct: float,
    daily_dd_pct: float,
    profit_target_pct: float,
    monte_carlo_runs: int,
) -> dict:
    if not trades:
        return {
            "trades_total": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "net_pnl": 0.0,
            "avg_pnl_per_trade": 0.0,
            "equity_curve": [],
            "drawdown_curve": [],
            "start_index_stats": {},
            "monte_carlo": {},
            "survivability": [],
        }

    pnl_sequence = [trade.pnl_usd for trade in trades]
    date_sequence = [trade.exit_ts for trade in trades]
    wins = sum(1 for value in pnl_sequence if value > 0)
    losses = sum(1 for value in pnl_sequence if value < 0)
    net_pnl = sum(pnl_sequence)
    win_rate = (wins / (wins + losses)) if (wins + losses) else None

    running = starting_balance
    equity_curve = [starting_balance]
    for pnl in pnl_sequence:
        running += pnl
        equity_curve.append(running)
    drawdown_curve = []
    peak = equity_curve[0]
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown_curve.append(((peak - equity) / peak) if peak else 0.0)

    start_results = []
    pass_count = 0
    fail_count = 0
    unresolved = 0
    trades_to_resolution: list[int] = []
    for start in range(len(trades)):
        segment_pnl = pnl_sequence[start:]
        segment_dates = date_sequence[start:]
        sim = _simulate_path(
            segment_pnl,
            segment_dates,
            starting_balance=starting_balance,
            max_dd_pct=max_dd_pct,
            daily_dd_pct=daily_dd_pct,
            profit_target_pct=profit_target_pct,
        )
        result = sim["result"]
        if result == "PASS_TARGET":
            pass_count += 1
        elif result.startswith("FAIL"):
            fail_count += 1
        else:
            unresolved += 1
        if sim["resolved_trade_count"] is not None:
            trades_to_resolution.append(sim["resolved_trade_count"])
        start_results.append(
            {
                "start_trade_no": trades[start].trade_no,
                "start_ts": trades[start].exit_ts.isoformat(),
                "result": result,
                "final_equity": sim["final_equity"],
                "max_drawdown_pct": sim["max_drawdown_pct"],
                "resolved_trade_count": sim["resolved_trade_count"],
            }
        )

    monte_results = []
    path_curves = []
    for _ in range(max(1, monte_carlo_runs)):
        shuffled = list(zip(pnl_sequence, date_sequence))
        random.shuffle(shuffled)
        shuffled_pnl = [item[0] for item in shuffled]
        shuffled_dates = [item[1] for item in shuffled]
        sim = _simulate_path(
            shuffled_pnl,
            shuffled_dates,
            starting_balance=starting_balance,
            max_dd_pct=max_dd_pct,
            daily_dd_pct=daily_dd_pct,
            profit_target_pct=profit_target_pct,
        )
        monte_results.append(sim)
        path_curves.append(sim["equity_curve"])

    monte_pass = sum(1 for item in monte_results if item["result"] == "PASS_TARGET")
    monte_fail = sum(1 for item in monte_results if item["result"].startswith("FAIL"))
    monte_open = len(monte_results) - monte_pass - monte_fail
    final_equities = [item["final_equity"] for item in monte_results]
    max_drawdowns = [item["max_drawdown_pct"] for item in monte_results]

    longest = max(len(curve) for curve in path_curves)
    p10_curve = []
    p50_curve = []
    p90_curve = []
    for step in range(longest):
        points = []
        for curve in path_curves:
            idx = min(step, len(curve) - 1)
            points.append(curve[idx])
        points.sort()
        lo = points[max(0, int(0.1 * (len(points) - 1)))]
        mid = points[int(0.5 * (len(points) - 1))]
        hi = points[min(len(points) - 1, int(0.9 * (len(points) - 1)))]
        p10_curve.append(lo)
        p50_curve.append(mid)
        p90_curve.append(hi)

    survivability = []
    for horizon in (10, 20, 30, 50, 100):
        alive = 0
        for curve in path_curves:
            if len(curve) - 1 >= horizon:
                alive += 1
        survivability.append(
            {
                "horizon_trades": horizon,
                "survival_rate": alive / len(path_curves) if path_curves else 0.0,
            }
        )

    return {
        "trades_total": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "net_pnl": net_pnl,
        "avg_pnl_per_trade": net_pnl / len(trades),
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "start_index_stats": {
            "pass_rate": pass_count / len(trades),
            "fail_rate": fail_count / len(trades),
            "unresolved_rate": unresolved / len(trades),
            "median_trades_to_resolution": median(trades_to_resolution) if trades_to_resolution else None,
            "samples": start_results,
        },
        "monte_carlo": {
            "runs": len(monte_results),
            "pass_rate": monte_pass / len(monte_results),
            "fail_rate": monte_fail / len(monte_results),
            "unresolved_rate": monte_open / len(monte_results),
            "final_equity_median": median(final_equities),
            "final_equity_min": min(final_equities),
            "final_equity_max": max(final_equities),
            "max_drawdown_median": median(max_drawdowns),
            "p10_curve": p10_curve,
            "p50_curve": p50_curve,
            "p90_curve": p90_curve,
        },
        "survivability": survivability,
    }
