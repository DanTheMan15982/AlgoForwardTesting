from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db import Database, EvalRow
from app.utils import et_day_key, et_midnight_for_day_key, next_et_midnight


def _build_eval_row(day_key: str, day_start_equity: float) -> EvalRow:
    window_start = et_midnight_for_day_key(day_key).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    return EvalRow(
        id=str(uuid4()),
        name="Test Eval",
        strategy_key="test",
        symbol="BTC",
        rules_json="{}",
        status="ACTIVE",
        created_at=now,
        risk_usd=50.0,
        starting_balance=10000.0,
        current_balance=10000.0,
        current_equity=day_start_equity,
        day_start_equity=day_start_equity,
        day_window_start_ts=window_start,
        last_daily_reset_day=day_key,
        max_dd_pct=0.06,
        daily_dd_pct=0.03,
        fees_enabled=1,
        slippage_enabled=1,
        taker_fee_rate=0.0004,
        slippage_min_usd=2.0,
        slippage_max_usd=20.0,
        risk_updated_at=now,
        profit_target_pct=None,
        passed_at=None,
        archived_at=None,
        stats_cache_json=None,
        fail_reason=None,
        max_dd_used_pct=0.0,
        worst_daily_dd_used_pct=0.0,
        latency_enabled=1,
        latency_min_sec=2,
        latency_max_sec=10,
        dynamic_tp_enabled=0,
        daily_dd_guard_enabled=0,
        daily_dd_guard_risk_multiple=1.0,
        daily_dd_guard_buffer_pct=0.1,
        daily_dd_guard_buffer_usd=0.0,
        daily_dd_guard_auto_resume_on_daily_reset=1,
        daily_dd_guard_close_open_positions_on_trigger=0,
        daily_dd_guard_blocking=0,
        daily_dd_guard_blocked_at=None,
        daily_dd_guard_reason=None,
    )


def test_et_day_key_boundary() -> None:
    before_midnight = datetime(2024, 5, 1, 3, 59, 59, tzinfo=timezone.utc)
    after_midnight = datetime(2024, 5, 1, 4, 0, 1, tzinfo=timezone.utc)
    assert et_day_key(before_midnight) == "2024-04-30"
    assert et_day_key(after_midnight) == "2024-05-01"


def test_et_day_key_dst_spring_forward() -> None:
    near_shift = datetime(2024, 3, 10, 6, 59, 59, tzinfo=timezone.utc)
    after_shift = datetime(2024, 3, 10, 7, 0, 1, tzinfo=timezone.utc)
    assert et_day_key(near_shift) == "2024-03-10"
    assert et_day_key(after_shift) == "2024-03-10"


def test_et_day_key_dst_fall_back() -> None:
    before_fall = datetime(2024, 11, 3, 5, 59, 59, tzinfo=timezone.utc)
    after_fall = datetime(2024, 11, 3, 6, 0, 1, tzinfo=timezone.utc)
    assert et_day_key(before_fall) == "2024-11-03"
    assert et_day_key(after_fall) == "2024-11-03"


def test_next_midnight_handles_dst() -> None:
    spring_day = datetime(2024, 3, 10, 5, 30, tzinfo=timezone.utc)
    spring_next = next_et_midnight(spring_day)
    spring_delta_hours = (spring_next - spring_day).total_seconds() / 3600
    assert spring_delta_hours != 24

    fall_day = datetime(2024, 11, 3, 4, 30, tzinfo=timezone.utc)
    fall_next = next_et_midnight(fall_day)
    fall_delta_hours = (fall_next - fall_day).total_seconds() / 3600
    assert fall_delta_hours != 24


def test_apply_daily_reset_if_needed(tmp_path) -> None:
    db = Database(str(tmp_path / "test.db"))
    db.init()
    eval_row = _build_eval_row("2024-05-01", 10000.0)
    db.insert_eval(eval_row)

    new_day_key = "2024-05-02"
    new_day_start = 10125.0
    updated = db.apply_daily_reset_if_needed(
        eval_row.id,
        new_day_key,
        new_day_start,
        et_midnight_for_day_key(new_day_key).isoformat(),
    )
    assert updated is True
    refreshed = db.fetch_eval(eval_row.id)
    assert refreshed is not None
    assert refreshed.day_start_equity == new_day_start
    assert refreshed.last_daily_reset_day == new_day_key

    updated_again = db.apply_daily_reset_if_needed(
        eval_row.id,
        new_day_key,
        9999.0,
        et_midnight_for_day_key(new_day_key).isoformat(),
    )
    assert updated_again is False
