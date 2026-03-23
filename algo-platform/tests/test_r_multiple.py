from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.analytics import compute_rr_metrics
from app.db import Database, EvalRow, PendingFillRow, PositionRow
from app.eval_manager import EvalManager
from app.price_service import PriceBar, PriceTick
from app.utils import compute_r_multiple, et_midnight_for_day_key


class DummyPriceService:
    def __init__(self, price: float, *, high: float | None = None, low: float | None = None) -> None:
        self._price = price
        self._high = high if high is not None else price
        self._low = low if low is not None else price

    def get_latest_bar(self, symbol: str) -> PriceBar:
        return PriceBar(
            ts=datetime.now(timezone.utc),
            symbol=symbol,
            timeframe="tick",
            open=self._price,
            high=self._high,
            low=self._low,
            close=self._price,
            source="test",
        )

    def get_latest_ticks(self) -> dict[str, PriceTick]:
        return {
            "BTC": PriceTick(ts=datetime.now(timezone.utc), price=self._price, source="test"),
            "ETH": PriceTick(ts=datetime.now(timezone.utc), price=self._price, source="test"),
            "SOL": PriceTick(ts=datetime.now(timezone.utc), price=self._price, source="test"),
        }


class DummyWS:
    async def broadcast(self, message) -> None:  # pragma: no cover - lightweight stub
        return None


def _build_eval(
    day_key: str,
    *,
    status: str = "ACTIVE",
    profit_target_pct: float | None = None,
    fees_enabled: int = 0,
    slippage_enabled: int = 0,
) -> EvalRow:
    now = datetime.now(timezone.utc).isoformat()
    return EvalRow(
        id=str(uuid4()),
        name="Test Eval",
        strategy_key="test",
        symbol="BTC",
        rules_json="{}",
        status=status,
        created_at=now,
        risk_usd=50.0,
        starting_balance=10000.0,
        current_balance=10000.0,
        current_equity=10000.0,
        day_start_equity=10000.0,
        day_window_start_ts=et_midnight_for_day_key(day_key).isoformat(),
        last_daily_reset_day=day_key,
        max_dd_pct=0.06,
        daily_dd_pct=0.03,
        fees_enabled=fees_enabled,
        slippage_enabled=slippage_enabled,
        taker_fee_rate=0.0004,
        slippage_min_usd=2.0,
        slippage_max_usd=20.0,
        risk_updated_at=now,
        profit_target_pct=profit_target_pct,
        passed_at=None,
        archived_at=None,
        stats_cache_json=None,
        fail_reason=None,
        max_dd_used_pct=0.0,
        worst_daily_dd_used_pct=0.0,
        latency_enabled=0,
        latency_min_sec=0,
        latency_max_sec=0,
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


def _build_position(eval_id: str) -> PositionRow:
    now = datetime.now(timezone.utc).isoformat()
    return PositionRow(
        id=str(uuid4()),
        eval_id=eval_id,
        symbol="BTC",
        side="LONG",
        qty=1.0,
        entry_price=100.0,
        stop_price=90.0,
        tp_price=110.0,
        tp_disabled=0,
        tp_source="WEBHOOK",
        opened_at=now,
        closed_at=None,
        status="OPEN",
        exit_price=None,
        r_multiple=None,
        pnl=None,
        fees=None,
        entry_fee=None,
        exit_fee=None,
        total_fees=None,
        entry_slippage=None,
        exit_slippage=None,
        entry_fill_price=100.0,
        exit_fill_price=None,
        risk_usd=50.0,
        reason=None,
        last_checked_ts=None,
        last_checked_price=None,
    )


def test_compute_r_multiple_long_short() -> None:
    assert float(compute_r_multiple("LONG", 100.0, 90.0, 110.0)) == pytest.approx(1.0)
    assert float(compute_r_multiple("LONG", 100.0, 90.0, 90.0)) == pytest.approx(-1.0)
    assert float(compute_r_multiple("SHORT", 100.0, 110.0, 90.0)) == pytest.approx(1.0)
    assert compute_r_multiple("LONG", 100.0, 100.0, 110.0) is None


def test_execute_close_sets_r_multiple(tmp_path) -> None:
    async def runner() -> None:
        db = Database(str(tmp_path / "test.db"))
        db.init()
        eval_row = _build_eval("2024-05-01")
        db.insert_eval(eval_row)
        position = _build_position(eval_row.id)
        db.insert_position(position)

        manager = EvalManager(db, DummyPriceService(105.0), DummyWS())
        manager._execute_close(
            eval_row=eval_row,
            position=position,
            action="CLOSE_MANUAL",
            intended_price=105.0,
            execution_price=105.0,
            latency_sec=0.0,
        )
        await asyncio.sleep(0)

        updated = db.fetch_position(position.id)
        assert updated is not None
        assert updated.r_multiple is not None

    asyncio.run(runner())


def test_compute_rr_metrics() -> None:
    base = _build_position("eval")
    rows = []
    for value in (1.0, -0.5, 2.0):
        rows.append(
            PositionRow(
                **{**base.__dict__, "id": str(uuid4()), "r_multiple": value, "status": "CLOSED"}
            )
        )
    metrics = compute_rr_metrics(rows)
    assert metrics["n_valid_r"] == 3
    assert metrics["n_wins_r"] == 2
    assert metrics["avg_win_r"] == 1.5
    assert metrics["win_rate_r"] == pytest.approx(66.6666, rel=1e-3)


def test_exit_all_sets_r_multiple(tmp_path) -> None:
    async def runner() -> None:
        db = Database(str(tmp_path / "test.db"))
        db.init()
        eval_row = _build_eval("2024-05-01")
        db.insert_eval(eval_row)
        position = _build_position(eval_row.id)
        db.insert_position(position)

        manager = EvalManager(db, DummyPriceService(105.0), DummyWS())
        manager._exit_all_for_eval(eval_row)
        await asyncio.sleep(0)

        updated = db.fetch_position(position.id)
        assert updated is not None
        assert updated.r_multiple is not None
        assert updated.status == "CLOSED"

    asyncio.run(runner())


def test_execute_open_applies_entry_fee_immediately(tmp_path) -> None:
    db = Database(str(tmp_path / "test.db"))
    db.init()
    eval_row = _build_eval("2024-05-01", fees_enabled=1, slippage_enabled=0)
    db.insert_eval(eval_row)

    manager = EvalManager(db, DummyPriceService(100.0), DummyWS())
    opened = manager._execute_open(
        eval_row=eval_row,
        side="LONG",
        qty=1.0,
        stop_price=90.0,
        tp_price=110.0,
        tp_disabled=False,
        intended_price=100.0,
        execution_price=100.0,
        latency_sec=0.0,
    )
    assert opened is True

    updated = db.fetch_eval(eval_row.id)
    assert updated is not None
    expected_entry_fee = 1.0 * 100.0 * eval_row.taker_fee_rate
    assert updated.current_balance == pytest.approx(eval_row.current_balance - expected_entry_fee)
    assert updated.current_equity == pytest.approx(eval_row.current_equity - expected_entry_fee)


def test_execute_close_does_not_double_charge_entry_fee(tmp_path) -> None:
    async def runner() -> None:
        db = Database(str(tmp_path / "test.db"))
        db.init()
        eval_row = _build_eval("2024-05-01", fees_enabled=1, slippage_enabled=0)
        db.insert_eval(eval_row)

        manager = EvalManager(db, DummyPriceService(100.0), DummyWS())
        manager._execute_open(
            eval_row=eval_row,
            side="LONG",
            qty=1.0,
            stop_price=90.0,
            tp_price=110.0,
            tp_disabled=False,
            intended_price=100.0,
            execution_price=100.0,
            latency_sec=0.0,
        )
        await asyncio.sleep(0)
        row_after_open = db.fetch_eval(eval_row.id)
        position = db.list_open_positions_for_eval(eval_row.id)[0]
        manager._execute_close(
            eval_row=row_after_open,
            position=position,
            action="CLOSE_MANUAL",
            intended_price=105.0,
            execution_price=105.0,
            latency_sec=0.0,
        )
        await asyncio.sleep(0)

        updated = db.fetch_eval(eval_row.id)
        assert updated is not None
        entry_fee = 1.0 * 100.0 * eval_row.taker_fee_rate
        exit_fee = 1.0 * 105.0 * eval_row.taker_fee_rate
        expected = 10000.0 + (105.0 - 100.0) - entry_fee - exit_fee
        assert updated.current_balance == pytest.approx(expected)
        assert updated.current_equity == pytest.approx(expected)

    asyncio.run(runner())


def test_paused_eval_daily_reset_runs_in_evaluate(tmp_path) -> None:
    async def runner() -> None:
        db = Database(str(tmp_path / "test.db"))
        db.init()
        eval_row = _build_eval("2024-01-01", status="PAUSED")
        db.insert_eval(eval_row)

        manager = EvalManager(db, DummyPriceService(100.0), DummyWS())
        await manager._evaluate()

        updated = db.fetch_eval(eval_row.id)
        assert updated is not None
        assert updated.last_daily_reset_day != "2024-01-01"

    asyncio.run(runner())


def test_paused_eval_risk_monitoring_closes_position(tmp_path) -> None:
    async def runner() -> None:
        db = Database(str(tmp_path / "test.db"))
        db.init()
        eval_row = _build_eval("2024-05-01", status="PAUSED")
        db.insert_eval(eval_row)
        position = _build_position(eval_row.id)
        db.insert_position(position)

        manager = EvalManager(db, DummyPriceService(110.0, high=111.0, low=109.0), DummyWS())
        await manager._evaluate()
        await asyncio.sleep(0)

        updated_position = db.fetch_position(position.id)
        assert updated_position is not None
        assert updated_position.status == "CLOSED"

    asyncio.run(runner())


def test_pending_open_cancelled_but_pending_close_executes_when_paused(tmp_path) -> None:
    async def runner() -> None:
        db = Database(str(tmp_path / "test.db"))
        db.init()
        eval_row = _build_eval("2024-05-01", status="PAUSED")
        db.insert_eval(eval_row)
        position = _build_position(eval_row.id)
        db.insert_position(position)
        now = datetime.now(timezone.utc).isoformat()
        open_fill_id = str(uuid4())
        db.insert_pending_fill(
            PendingFillRow(
                id=open_fill_id,
                eval_id=eval_row.id,
                position_id=None,
                action="OPEN",
                side="LONG",
                qty=1.0,
                intended_price=100.0,
                stop_price=90.0,
                tp_price=110.0,
                scheduled_ts=now,
                created_ts=now,
                status="PENDING",
            )
        )
        close_fill_id = str(uuid4())
        db.insert_pending_fill(
            PendingFillRow(
                id=close_fill_id,
                eval_id=eval_row.id,
                position_id=position.id,
                action="CLOSE_TP",
                side="LONG",
                qty=position.qty,
                intended_price=110.0,
                stop_price=position.stop_price,
                tp_price=position.tp_price,
                scheduled_ts=now,
                created_ts=now,
                status="PENDING",
            )
        )

        manager = EvalManager(db, DummyPriceService(110.0), DummyWS())
        manager._feed_state["BTC"] = "FRESH"
        await manager._process_pending_fills()
        await asyncio.sleep(0)

        fills = {fill.id: fill for fill in db.list_pending_fills_due("9999-12-31T00:00:00+00:00")}
        # Due list only returns pending fills, so open should be cancelled and close should be executed.
        assert close_fill_id not in fills
        with db._lock:
            rows = db._conn.execute("SELECT id, status FROM pending_fills").fetchall()
        fill_statuses = {row["id"]: row["status"] for row in rows}
        assert fill_statuses[open_fill_id] == "CANCELLED"
        assert fill_statuses[close_fill_id] == "EXECUTED"
        updated_position = db.fetch_position(position.id)
        assert updated_position is not None
        assert updated_position.status == "CLOSED"

    asyncio.run(runner())


def test_profit_target_can_pass_on_same_update_after_position_close(tmp_path) -> None:
    async def runner() -> None:
        db = Database(str(tmp_path / "test.db"))
        db.init()
        eval_row = _build_eval("2024-05-01", profit_target_pct=0.0001)
        db.insert_eval(eval_row)
        position = _build_position(eval_row.id)
        db.insert_position(position)

        manager = EvalManager(db, DummyPriceService(110.0, high=111.0, low=109.0), DummyWS())
        manager._feed_state["BTC"] = "FRESH"
        await manager._update_eval(eval_row, [position])
        await asyncio.sleep(0)

        updated = db.fetch_eval(eval_row.id)
        assert updated is not None
        assert updated.status == "PASSED"

    asyncio.run(runner())
