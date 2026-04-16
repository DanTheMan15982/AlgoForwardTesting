from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import random
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from .db import (
    Database,
    EvalRow,
    EventRow,
    PositionRow,
    PendingFillRow,
    EquityPointRow,
    utc_iso,
    utc_now,
)
from .models import EvalStatus, EventType, Side, TradingViewPayload
from .price_service import PriceService
from .analytics import (
    summarize_eval,
    normalize_profit_target_pct,
    derive_strategy_family,
    build_ruleset,
    ruleset_hash,
)
from .realtime import WebSocketManager, WSMessage
from .utils import (
    compute_r_multiple,
    evaluate_crossing,
    et_day_key,
    et_midnight_for_day_key,
    map_ticker_to_symbol,
    validate_payload,
)


class EvalManager:
    def __init__(self, db: Database, price_service: PriceService, ws: WebSocketManager) -> None:
        self._db = db
        self._price_service = price_service
        self._ws = ws
        self._logger = logging.getLogger("eval_manager")
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._exec_task: Optional[asyncio.Task[None]] = None
        self._feed_state: dict[str, str] = {"BTC": "STALE", "ETH": "STALE", "SOL": "STALE"}
        self._stale_after_seconds = 30

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        self._exec_task = asyncio.create_task(self._run_executor())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._exec_task:
            self._exec_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._exec_task

    def create_eval(
        self,
        name: str,
        strategy_key: str,
        account_type: str,
        prop_firm_mode: Optional[str],
        symbol: str,
        starting_balance: float,
        risk_usd: float,
        fees_enabled: bool,
        slippage_enabled: bool,
        taker_fee_rate: float,
        slippage_min_usd: float,
        slippage_max_usd: float,
        max_dd_pct: float,
        daily_dd_pct: float,
        profit_target_pct: Optional[float],
        latency_enabled: bool,
        latency_min_sec: int,
        latency_max_sec: int,
        dynamic_tp_enabled: bool,
        webhook_passthrough_enabled: bool,
        webhook_passthrough_url: Optional[str],
    ) -> EvalRow:
        now = utc_iso()
        now_utc = utc_now()
        day_key = et_day_key(now_utc)
        window_start = et_midnight_for_day_key(day_key)
        eval_id = str(uuid4())
        row = EvalRow(
            id=eval_id,
            name=name,
            strategy_key=strategy_key,
            account_type=account_type,
            prop_firm_mode=prop_firm_mode,
            symbol=symbol,
            rules_json=json.dumps({"max_dd_pct": max_dd_pct, "daily_dd_pct": daily_dd_pct}),
            status=EvalStatus.ACTIVE.value,
            created_at=now,
            starting_balance=starting_balance,
            current_balance=starting_balance,
            current_equity=starting_balance,
            day_start_equity=starting_balance,
            day_window_start_ts=window_start.isoformat(),
            last_daily_reset_day=day_key,
            max_dd_pct=max_dd_pct,
            daily_dd_pct=daily_dd_pct,
            risk_usd=risk_usd,
            fees_enabled=1 if fees_enabled else 0,
            slippage_enabled=1 if slippage_enabled else 0,
            taker_fee_rate=taker_fee_rate,
            slippage_min_usd=slippage_min_usd,
            slippage_max_usd=slippage_max_usd,
            risk_updated_at=now,
            profit_target_pct=profit_target_pct,
            passed_at=None,
            archived_at=None,
            stats_cache_json=None,
            fail_reason=None,
            max_dd_used_pct=0.0,
            worst_daily_dd_used_pct=0.0,
            latency_enabled=1 if latency_enabled else 0,
            latency_min_sec=latency_min_sec,
            latency_max_sec=latency_max_sec,
            dynamic_tp_enabled=1 if dynamic_tp_enabled else 0,
            webhook_passthrough_enabled=1 if webhook_passthrough_enabled else 0,
            webhook_passthrough_url=webhook_passthrough_url,
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
        self._db.insert_eval(row)
        self._db.insert_event(
            EventRow(
                id=str(uuid4()),
                eval_id=eval_id,
                ts=now,
                type=EventType.HEARTBEAT.value,
                payload_json=json.dumps({"message": "eval created"}),
            )
        )
        asyncio.create_task(
            self._ws.broadcast(
                WSMessage(
                    type="eval_created",
                    data={"eval_id": eval_id, "name": name, "strategy_key": strategy_key, "symbol": symbol},
                )
            )
        )
        return row

    def route_signal(
        self,
        strategy_key: str,
        symbol: str,
        payload: TradingViewPayload,
    ) -> int:
        validate_payload(payload)
        evals = [
            row
            for row in self._db.list_active_evals()
            if row.strategy_key == strategy_key and row.symbol == symbol
        ]
        for row in evals:
            self._handle_signal_for_eval(row, payload)
        return len(evals)

    def exit_all_positions(self, strategy_key: str) -> int:
        evals = [row for row in self._db.list_evals() if row.strategy_key == strategy_key]
        for row in evals:
            self._exit_all_for_eval(row)
        return len(evals)

    def pause_eval(self, eval_id: str) -> Optional[EvalRow]:
        row = self._db.fetch_eval(eval_id)
        if not row:
            return None
        self._db.update_eval_status(eval_id, EvalStatus.PAUSED.value)
        self._cancel_pending_fills(eval_id, "eval paused")
        updated = self._db.fetch_eval(eval_id)
        if updated:
            asyncio.create_task(
                self._ws.broadcast(
                    WSMessage(
                        type="eval_update",
                        data={"eval_id": updated.id, "status": updated.status},
                    )
                )
            )
        return updated

    def resume_eval(self, eval_id: str) -> Optional[EvalRow]:
        row = self._db.fetch_eval(eval_id)
        if not row:
            return None
        self._db.update_eval_status(eval_id, EvalStatus.ACTIVE.value)
        updated = self._db.fetch_eval(eval_id)
        if updated:
            asyncio.create_task(
                self._ws.broadcast(
                    WSMessage(
                        type="eval_update",
                        data={"eval_id": updated.id, "status": updated.status},
                    )
                )
            )
        return updated

    def _cancel_pending_fills(self, eval_id: str, reason: str) -> None:
        cancelled = self._db.cancel_pending_fills(eval_id)
        for fill in cancelled:
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_id,
                    ts=utc_iso(),
                    type=EventType.ORDER_CANCELLED.value,
                    payload_json=json.dumps(
                        {
                            "pending_fill_id": fill.id,
                            "action": fill.action,
                            "reason": reason,
                        }
                    ),
                )
            )

    def _maybe_apply_daily_reset(
        self,
        eval_row: EvalRow,
        now_utc: datetime,
        current_equity: float,
    ) -> EvalRow:
        day_key = et_day_key(now_utc)
        if eval_row.last_daily_reset_day == day_key:
            return eval_row
        day_window_start = et_midnight_for_day_key(day_key)
        updated = self._db.apply_daily_reset_if_needed(
            eval_row.id,
            day_key,
            current_equity,
            day_window_start.isoformat(),
        )
        if updated:
            now_et = now_utc.astimezone(day_window_start.tzinfo)
            prev_daily_used_pct = (
                max(0.0, (eval_row.day_start_equity - current_equity) / eval_row.day_start_equity)
                if eval_row.day_start_equity
                else 0.0
            )
            self._logger.info(
                "daily_reset_applied eval=%s day_key=%s now_utc=%s now_et=%s prev_day_start_equity=%.2f new_day_start_equity=%.2f prev_daily_used_pct=%.4f new_daily_used_pct=0.0000",
                eval_row.id,
                day_key,
                now_utc.isoformat(),
                now_et.isoformat(),
                eval_row.day_start_equity,
                current_equity,
                prev_daily_used_pct,
            )
            return EvalRow(
                id=eval_row.id,
                name=eval_row.name,
                strategy_key=eval_row.strategy_key,
                account_type=eval_row.account_type,
                prop_firm_mode=eval_row.prop_firm_mode,
                symbol=eval_row.symbol,
                rules_json=eval_row.rules_json,
                status=eval_row.status,
                created_at=eval_row.created_at,
                starting_balance=eval_row.starting_balance,
                risk_usd=eval_row.risk_usd,
                current_balance=eval_row.current_balance,
                current_equity=eval_row.current_equity,
                day_start_equity=current_equity,
                day_window_start_ts=day_window_start.isoformat(),
                last_daily_reset_day=day_key,
                max_dd_pct=eval_row.max_dd_pct,
                daily_dd_pct=eval_row.daily_dd_pct,
                fees_enabled=eval_row.fees_enabled,
                slippage_enabled=eval_row.slippage_enabled,
                taker_fee_rate=eval_row.taker_fee_rate,
                slippage_min_usd=eval_row.slippage_min_usd,
                slippage_max_usd=eval_row.slippage_max_usd,
                risk_updated_at=eval_row.risk_updated_at,
                profit_target_pct=eval_row.profit_target_pct,
                passed_at=eval_row.passed_at,
                archived_at=eval_row.archived_at,
                stats_cache_json=eval_row.stats_cache_json,
                fail_reason=eval_row.fail_reason,
                max_dd_used_pct=eval_row.max_dd_used_pct,
                worst_daily_dd_used_pct=eval_row.worst_daily_dd_used_pct,
                latency_enabled=eval_row.latency_enabled,
                latency_min_sec=eval_row.latency_min_sec,
                latency_max_sec=eval_row.latency_max_sec,
                dynamic_tp_enabled=eval_row.dynamic_tp_enabled,
                webhook_passthrough_enabled=eval_row.webhook_passthrough_enabled,
                webhook_passthrough_url=eval_row.webhook_passthrough_url,
                daily_dd_guard_enabled=eval_row.daily_dd_guard_enabled,
                daily_dd_guard_risk_multiple=eval_row.daily_dd_guard_risk_multiple,
                daily_dd_guard_buffer_pct=eval_row.daily_dd_guard_buffer_pct,
                daily_dd_guard_buffer_usd=eval_row.daily_dd_guard_buffer_usd,
                daily_dd_guard_auto_resume_on_daily_reset=eval_row.daily_dd_guard_auto_resume_on_daily_reset,
                daily_dd_guard_close_open_positions_on_trigger=eval_row.daily_dd_guard_close_open_positions_on_trigger,
                daily_dd_guard_blocking=eval_row.daily_dd_guard_blocking,
                daily_dd_guard_blocked_at=eval_row.daily_dd_guard_blocked_at,
                daily_dd_guard_reason=eval_row.daily_dd_guard_reason,
            )
        refreshed = self._db.fetch_eval(eval_row.id)
        return refreshed or eval_row

    def _exit_all_for_eval(self, eval_row: EvalRow) -> None:
        now = utc_iso()
        open_positions = self._db.list_open_positions_for_eval(eval_row.id)
        self._db.insert_event(
            EventRow(
                id=str(uuid4()),
                eval_id=eval_row.id,
                ts=now,
                type=EventType.EXIT_ALL_RECEIVED.value,
                payload_json=json.dumps(
                    {
                        "open_positions": len(open_positions),
                        "message": "exit received but no open positions" if not open_positions else "exit received",
                    }
                ),
            )
        )
        self._cancel_pending_fills(eval_row.id, "exit-all received")
        if not open_positions:
            return
        for position in open_positions:
            bar = self._price_service.get_latest_bar(position.symbol)
            intended_price = bar.close if bar else position.entry_price
            if bool(eval_row.latency_enabled):
                self._schedule_pending_close(eval_row, position, "CLOSE_EXIT_ALL", intended_price)
            else:
                self._execute_close(
                    eval_row=eval_row,
                    position=position,
                    action="CLOSE_EXIT_ALL",
                    intended_price=intended_price,
                    execution_price=intended_price,
                    latency_sec=0.0,
                )

    def _handle_signal_for_eval(self, eval_row: EvalRow, payload: TradingViewPayload) -> None:
        now = utc_iso()
        self._db.insert_event(
            EventRow(
                id=str(uuid4()),
                eval_id=eval_row.id,
                ts=now,
                type=EventType.SIGNAL_RECEIVED.value,
                payload_json=json.dumps(payload.model_dump()),
            )
        )

        if eval_row.status in (EvalStatus.PASSED.value, EvalStatus.FAILED.value):
            return

        eval_row = self._maybe_apply_daily_reset(eval_row, utc_now(), eval_row.current_equity)
        eval_row = self._refresh_daily_dd_guard(eval_row, eval_row.current_equity)
        if bool(eval_row.daily_dd_guard_blocking):
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_row.id,
                    ts=utc_iso(),
                    type=EventType.DAILY_DD_GUARD_BLOCKED_ENTRY.value,
                    payload_json=json.dumps(
                        {
                            "reason": eval_row.daily_dd_guard_reason or "daily dd guard blocking",
                            "current_equity": eval_row.current_equity,
                        }
                    ),
                )
            )
            return

        entry_price = payload.entry
        if entry_price is None:
            bar = self._price_service.get_latest_bar(eval_row.symbol)
            if not bar:
                self._log_invalid_trade(
                    eval_row,
                    payload,
                    None,
                    "price unavailable for validation",
                )
                return
            entry_price = bar.close

        if self._feed_state.get(eval_row.symbol) == "STALE":
            self._log_invalid_trade(
                eval_row,
                payload,
                entry_price,
                "price feed stale",
            )
            return

        signal_key = self._signal_dedupe_key(eval_row.strategy_key, eval_row.symbol, payload, now)
        inserted = self._db.insert_signal(
            signal_key,
            eval_row.id,
            eval_row.strategy_key,
            eval_row.symbol,
            now,
            json.dumps(payload.model_dump()),
        )
        if not inserted:
            self._logger.info(
                "[DUPLICATE_SIGNAL] strategy=%s symbol=%s signal_id=%s",
                eval_row.strategy_key,
                eval_row.symbol,
                signal_key,
            )
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_row.id,
                    ts=now,
                    type=EventType.DUPLICATE_SIGNAL_IGNORED.value,
                    payload_json=json.dumps(
                        {
                            "signal_id": signal_key,
                            "strategy_key": eval_row.strategy_key,
                            "symbol": eval_row.symbol,
                        }
                    ),
                )
            )
            return

        dynamic_tp_enabled = bool(eval_row.dynamic_tp_enabled)
        is_valid, reason = validate_trade_signal(
            payload.side.value,
            entry_price,
            payload.stop,
            payload.tp,
            dynamic_tp_enabled,
        )
        if not is_valid:
            self._log_invalid_trade(eval_row, payload, entry_price, reason)
            return

        tp_disabled = dynamic_tp_enabled
        tp_price = None if tp_disabled else payload.tp
        qty = self._calculate_qty(eval_row.risk_usd, entry_price, payload.stop)
        if qty is None:
            self._log_invalid_trade(
                eval_row,
                payload,
                entry_price,
                "invalid stop distance",
            )
            return
        if bool(eval_row.latency_enabled):
            self._schedule_pending_open(eval_row, payload, qty, entry_price, tp_price)
            return

        self._execute_open(
            eval_row=eval_row,
            side=payload.side.value,
            qty=qty,
            stop_price=payload.stop,
            tp_price=tp_price,
            tp_disabled=tp_disabled,
            intended_price=entry_price,
            execution_price=entry_price,
            latency_sec=0.0,
        )

    def _log_invalid_trade(
        self,
        eval_row: EvalRow,
        payload: TradingViewPayload,
        entry_price: Optional[float],
        reason: str,
    ) -> None:
        self._logger.warning(
            "[INVALID_TRADE] eval=%s strategy=%s symbol=%s reason=%s",
            eval_row.id,
            eval_row.strategy_key,
            eval_row.symbol,
            reason,
        )
        self._db.insert_event(
            EventRow(
                id=str(uuid4()),
                eval_id=eval_row.id,
                ts=utc_iso(),
                type=EventType.INVALID_TRADE_REJECTED.value,
                payload_json=json.dumps(
                    {
                        "reason": reason,
                        "side": payload.side.value,
                        "entry": entry_price,
                        "stop": payload.stop,
                        "tp": payload.tp,
                        "strategy_key": eval_row.strategy_key,
                        "symbol": eval_row.symbol,
                        "eval_id": eval_row.id,
                    }
                ),
            )
        )

    def _random_latency_sec(self, min_sec: int, max_sec: int) -> float:
        if max_sec <= min_sec:
            return float(min_sec)
        return random.uniform(min_sec, max_sec)

    def _schedule_pending_open(
        self,
        eval_row: EvalRow,
        payload: TradingViewPayload,
        qty: float,
        intended_price: float,
        tp_price: Optional[float],
    ) -> None:
        latency_sec = self._random_latency_sec(eval_row.latency_min_sec, eval_row.latency_max_sec)
        now = utc_now()
        scheduled_ts = (now + timedelta(seconds=latency_sec)).isoformat()
        row = PendingFillRow(
            id=str(uuid4()),
            eval_id=eval_row.id,
            position_id=None,
            action="OPEN",
            side=payload.side.value,
            qty=qty,
            intended_price=intended_price,
            stop_price=payload.stop,
            tp_price=tp_price,
            scheduled_ts=scheduled_ts,
            created_ts=now.isoformat(),
            status="PENDING",
        )
        self._db.insert_pending_fill(row)
        self._db.insert_event(
            EventRow(
                id=str(uuid4()),
                eval_id=eval_row.id,
                ts=utc_iso(),
                type=EventType.ORDER_SCHEDULED.value,
                payload_json=json.dumps(
                    {
                        "action": "OPEN",
                        "intended_price": intended_price,
                        "scheduled_ts": scheduled_ts,
                        "latency_sec": latency_sec,
                    }
                ),
            )
        )
        self._logger.info(
            "[ORDER_SCHEDULED] eval=%s action=OPEN latency=%.2fs scheduled=%s",
            eval_row.id,
            latency_sec,
            scheduled_ts,
        )

    def _schedule_pending_close(
        self,
        eval_row: EvalRow,
        position: PositionRow,
        action: str,
        intended_price: float,
    ) -> None:
        if self._db.has_pending_fill_for_position(position.id):
            return
        latency_sec = self._random_latency_sec(eval_row.latency_min_sec, eval_row.latency_max_sec)
        now = utc_now()
        scheduled_ts = (now + timedelta(seconds=latency_sec)).isoformat()
        row = PendingFillRow(
            id=str(uuid4()),
            eval_id=eval_row.id,
            position_id=position.id,
            action=action,
            side=position.side,
            qty=position.qty,
            intended_price=intended_price,
            stop_price=position.stop_price,
            tp_price=position.tp_price,
            scheduled_ts=scheduled_ts,
            created_ts=now.isoformat(),
            status="PENDING",
        )
        self._db.insert_pending_fill(row)
        self._db.insert_event(
            EventRow(
                id=str(uuid4()),
                eval_id=eval_row.id,
                ts=utc_iso(),
                type=EventType.ORDER_SCHEDULED.value,
                payload_json=json.dumps(
                    {
                        "action": action,
                        "position_id": position.id,
                        "intended_price": intended_price,
                        "scheduled_ts": scheduled_ts,
                        "latency_sec": latency_sec,
                    }
                ),
            )
        )
        self._logger.info(
            "[ORDER_SCHEDULED] eval=%s action=%s position=%s latency=%.2fs scheduled=%s",
            eval_row.id,
            action,
            position.id,
            latency_sec,
            scheduled_ts,
        )

    def _execute_open_from_pending(self, eval_row: EvalRow, fill: PendingFillRow) -> bool:
        bar = self._price_service.get_latest_bar(eval_row.symbol)
        if not bar:
            return False
        if fill.stop_price is None:
            return False
        eval_row = self._maybe_apply_daily_reset(eval_row, utc_now(), eval_row.current_equity)
        eval_row = self._refresh_daily_dd_guard(eval_row, eval_row.current_equity)
        if bool(eval_row.daily_dd_guard_blocking):
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_row.id,
                    ts=utc_iso(),
                    type=EventType.ORDER_CANCELLED.value,
                    payload_json=json.dumps(
                        {
                            "pending_fill_id": fill.id,
                            "action": "OPEN",
                            "reason": "daily dd guard blocking",
                        }
                    ),
                )
            )
            return False
        latency_sec = (
            datetime.fromisoformat(fill.scheduled_ts) - datetime.fromisoformat(fill.created_ts)
        ).total_seconds()
        return self._execute_open(
            eval_row=eval_row,
            side=fill.side,
            qty=fill.qty,
            stop_price=fill.stop_price,
            tp_price=fill.tp_price,
            tp_disabled=fill.tp_price is None,
            intended_price=fill.intended_price,
            execution_price=bar.close,
            latency_sec=latency_sec,
        )

    def _execute_open(
        self,
        eval_row: EvalRow,
        side: str,
        qty: float,
        stop_price: float,
        tp_price: Optional[float],
        tp_disabled: bool,
        intended_price: float,
        execution_price: float,
        latency_sec: float,
    ) -> bool:
        entry_slippage = (
            self._random_slippage(eval_row.slippage_min_usd, eval_row.slippage_max_usd)
            if bool(eval_row.slippage_enabled)
            else 0.0
        )
        entry_fill_price = self._apply_slippage(side, execution_price, entry_slippage, is_entry=True)
        entry_fee = (
            self._calculate_fee(qty, entry_fill_price, eval_row.taker_fee_rate)
            if bool(eval_row.fees_enabled)
            else 0.0
        )
        position = PositionRow(
            id=str(uuid4()),
            eval_id=eval_row.id,
            symbol=eval_row.symbol,
            side=side,
            qty=qty,
            entry_price=execution_price,
            stop_price=stop_price,
            tp_price=tp_price,
            tp_disabled=1 if tp_disabled else 0,
            tp_source="DISABLED_DYNAMIC_TP" if tp_disabled else "WEBHOOK",
            opened_at=utc_iso(),
            closed_at=None,
            status="OPEN",
            exit_price=None,
            r_multiple=None,
            pnl=None,
            fees=None,
            entry_fee=entry_fee,
            exit_fee=None,
            total_fees=entry_fee,
            entry_slippage=entry_slippage,
            exit_slippage=None,
            entry_fill_price=entry_fill_price,
            exit_fill_price=None,
            risk_usd=eval_row.risk_usd,
            reason=None,
            last_checked_ts=None,
            last_checked_price=None,
        )
        event_payload = json.dumps(
            {
                "position_id": position.id,
                "action": "OPEN",
                "intended_price": intended_price,
                "execution_price": execution_price,
                "entry_fill_price": entry_fill_price,
                "stop_price": stop_price,
                "tp_price": tp_price,
                "tp_disabled": tp_disabled,
                "qty": position.qty,
                "risk_usd": eval_row.risk_usd,
                "entry_fee": entry_fee,
                "entry_slippage": entry_slippage,
                "latency_sec": latency_sec,
            }
        )
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO positions (
                    id, eval_id, symbol, side, qty, entry_price, stop_price, tp_price,
                    tp_disabled, tp_source, opened_at, closed_at, status, exit_price, r_multiple, pnl, fees,
                    entry_fee, exit_fee, total_fees, entry_slippage, exit_slippage,
                    entry_fill_price, exit_fill_price, risk_usd, reason,
                    last_checked_ts, last_checked_price
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.id,
                    position.eval_id,
                    position.symbol,
                    position.side,
                    position.qty,
                    position.entry_price,
                    position.stop_price,
                    position.tp_price,
                    position.tp_disabled,
                    position.tp_source,
                    position.opened_at,
                    position.closed_at,
                    position.status,
                    position.exit_price,
                    position.r_multiple,
                    position.pnl,
                    position.fees,
                    position.entry_fee,
                    position.exit_fee,
                    position.total_fees,
                    position.entry_slippage,
                    position.exit_slippage,
                    position.entry_fill_price,
                    position.exit_fill_price,
                    position.risk_usd,
                    position.reason,
                    position.last_checked_ts,
                    position.last_checked_price,
                ),
            )
            conn.execute(
                "INSERT INTO events (id, eval_id, ts, type, payload_json) VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), eval_row.id, utc_iso(), EventType.ORDER_EXECUTED.value, event_payload),
            )
            conn.execute(
                """
                UPDATE evals
                SET current_balance = ?, current_equity = ?
                WHERE id = ?
                """,
                (
                    eval_row.current_balance - entry_fee,
                    eval_row.current_equity - entry_fee,
                    eval_row.id,
                ),
            )
        asyncio.create_task(
            self._ws.broadcast(
                WSMessage(
                    type="position_opened",
                    data={
                        "eval_id": eval_row.id,
                        "position_id": position.id,
                        "symbol": position.symbol,
                        "side": position.side,
                        "entry_price": execution_price,
                        "stop_price": stop_price,
                        "tp_price": tp_price,
                    },
                )
            )
        )
        return True

    def _execute_close_from_pending(self, eval_row: EvalRow, fill: PendingFillRow) -> bool:
        if not fill.position_id:
            return False
        position = self._db.fetch_position(fill.position_id)
        if not position or position.status != "OPEN":
            return False
        bar = self._price_service.get_latest_bar(position.symbol)
        if not bar:
            return False
        latency_sec = (
            datetime.fromisoformat(fill.scheduled_ts) - datetime.fromisoformat(fill.created_ts)
        ).total_seconds()
        return self._execute_close(
            eval_row=eval_row,
            position=position,
            action=fill.action,
            intended_price=fill.intended_price,
            execution_price=bar.close,
            latency_sec=latency_sec,
        )

    def _execute_close(
        self,
        eval_row: EvalRow,
        position: PositionRow,
        action: str,
        intended_price: float,
        execution_price: float,
        latency_sec: float,
    ) -> bool:
        now_utc = utc_now()
        eval_row = self._maybe_apply_daily_reset(eval_row, now_utc, eval_row.current_equity)
        position_side = Side(position.side)
        exit_slippage = (
            self._random_slippage(eval_row.slippage_min_usd, eval_row.slippage_max_usd)
            if bool(eval_row.slippage_enabled)
            else 0.0
        )
        exit_fill_price = self._apply_slippage(
            position_side.value, execution_price, exit_slippage, is_entry=False
        )
        exit_fee = (
            self._calculate_fee(position.qty, exit_fill_price, eval_row.taker_fee_rate)
            if bool(eval_row.fees_enabled)
            else 0.0
        )
        total_fees = (position.entry_fee or 0.0) + exit_fee
        pnl = self._calculate_pnl(
            position_side,
            position.entry_fill_price or position.entry_price,
            exit_fill_price,
            position.qty,
        ) - total_fees
        realized_delta = pnl + (position.entry_fee or 0.0)
        reason = "TP" if action == "CLOSE_TP" else "STOP" if action == "CLOSE_SL" else "MANUAL"
        r_multiple_value = compute_r_multiple(
            position.side,
            position.entry_price,
            position.stop_price,
            execution_price,
        )
        r_multiple = float(r_multiple_value) if r_multiple_value is not None else None
        if r_multiple_value is None:
            self._logger.warning(
                "r_multiple_missing eval=%s position=%s side=%s entry=%.6f stop=%.6f exit=%.6f",
                eval_row.id,
                position.id,
                position.side,
                position.entry_price,
                position.stop_price,
                execution_price,
            )
        self._db.close_position(
            position.id,
            utc_iso(),
            execution_price,
            r_multiple,
            pnl,
            total_fees,
            exit_fee,
            total_fees,
            exit_slippage,
            exit_fill_price,
            reason,
        )
        self._logger.info(
            "trade_closed eval=%s position=%s side=%s entry=%.6f stop=%.6f exit=%.6f r_multiple=%s pnl=%.2f",
            eval_row.id,
            position.id,
            position.side,
            position.entry_price,
            position.stop_price,
            execution_price,
            f"{r_multiple:.4f}" if r_multiple is not None else "null",
            pnl,
        )
        new_balance = eval_row.current_balance + realized_delta
        new_equity = eval_row.current_equity + realized_delta
        self._db.update_eval_financials(
            eval_row.id,
            new_balance,
            new_equity,
            eval_row.day_start_equity,
            eval_row.day_window_start_ts,
        )
        self._db.insert_event(
            EventRow(
                id=str(uuid4()),
                eval_id=eval_row.id,
                ts=utc_iso(),
                type=EventType.ORDER_EXECUTED.value,
                payload_json=json.dumps(
                    {
                        "position_id": position.id,
                        "action": action,
                        "intended_price": intended_price,
                        "execution_price": execution_price,
                        "exit_fill_price": exit_fill_price,
                        "pnl": pnl,
                        "exit_fee": exit_fee,
                        "exit_slippage": exit_slippage,
                        "latency_sec": latency_sec,
                        "r_multiple": r_multiple,
                    }
                ),
            )
        )
        if reason in ("TP", "STOP"):
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_row.id,
                    ts=utc_iso(),
                    type=EventType.TP_HIT.value if reason == "TP" else EventType.STOP_HIT.value,
                    payload_json=json.dumps(
                        {
                            "position_id": position.id,
                            "exit_price": execution_price,
                            "exit_fill_price": exit_fill_price,
                            "pnl": pnl,
                            "exit_fee": exit_fee,
                            "exit_slippage": exit_slippage,
                        }
                    ),
                )
            )
        if action == "CLOSE_EXIT_ALL":
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_row.id,
                    ts=utc_iso(),
                    type=EventType.POSITION_CLOSED_EXIT_ALL.value,
                    payload_json=json.dumps(
                        {
                            "position_id": position.id,
                            "exit_price": execution_price,
                            "exit_fill_price": exit_fill_price,
                            "pnl": pnl,
                            "total_fees": total_fees,
                            "exit_fee": exit_fee,
                            "exit_slippage": exit_slippage,
                            "latency_sec": latency_sec,
                        }
                    ),
                )
            )
        asyncio.create_task(
            self._ws.broadcast(
                WSMessage(
                    type="position_closed",
                    data={
                        "eval_id": eval_row.id,
                        "position_id": position.id,
                        "exit_price": execution_price,
                        "pnl": pnl,
                        "reason": reason,
                    },
                )
            )
        )
        return True

    async def _run(self) -> None:
        while self._running:
            try:
                await self._evaluate()
            except Exception:
                self._logger.exception("eval loop iteration failed")
            await asyncio.sleep(2.0)

    async def _run_executor(self) -> None:
        while self._running:
            try:
                await self._process_pending_fills()
            except Exception:
                self._logger.exception("pending fill executor iteration failed")
            await asyncio.sleep(1.0)

    async def _process_pending_fills(self) -> None:
        now = utc_iso()
        for fill in self._db.list_pending_fills_due(now):
            try:
                eval_row = self._db.fetch_eval(fill.eval_id)
                if not eval_row:
                    self._db.update_pending_fill_status(fill.id, "CANCELLED")
                    self._db.insert_event(
                        EventRow(
                            id=str(uuid4()),
                            eval_id=fill.eval_id,
                            ts=utc_iso(),
                            type=EventType.ORDER_CANCELLED.value,
                            payload_json=json.dumps(
                                {
                                    "pending_fill_id": fill.id,
                                    "action": fill.action,
                                    "reason": "eval not found",
                                }
                            ),
                        )
                    )
                    continue
                is_open_action = fill.action == "OPEN"
                if is_open_action and eval_row.status != EvalStatus.ACTIVE.value:
                    self._db.update_pending_fill_status(fill.id, "CANCELLED")
                    self._db.insert_event(
                        EventRow(
                            id=str(uuid4()),
                            eval_id=fill.eval_id,
                            ts=utc_iso(),
                            type=EventType.ORDER_CANCELLED.value,
                            payload_json=json.dumps(
                                {
                                    "pending_fill_id": fill.id,
                                    "action": fill.action,
                                    "reason": "eval not active for open",
                                }
                            ),
                        )
                    )
                    continue
                if (not is_open_action) and eval_row.status not in (
                    EvalStatus.ACTIVE.value,
                    EvalStatus.PAUSED.value,
                ):
                    self._db.update_pending_fill_status(fill.id, "CANCELLED")
                    self._db.insert_event(
                        EventRow(
                            id=str(uuid4()),
                            eval_id=fill.eval_id,
                            ts=utc_iso(),
                            type=EventType.ORDER_CANCELLED.value,
                            payload_json=json.dumps(
                                {
                                    "pending_fill_id": fill.id,
                                    "action": fill.action,
                                    "reason": "eval not active or paused for close",
                                }
                            ),
                        )
                    )
                    continue
                if self._feed_state.get(eval_row.symbol) == "STALE":
                    if fill.action != "CLOSE_EXIT_ALL":
                        self._logger.info(
                            "[ORDER_DELAYED] eval=%s action=%s reason=price feed stale",
                            eval_row.id,
                            fill.action,
                        )
                        continue
                if is_open_action:
                    eval_row = self._refresh_daily_dd_guard(eval_row, eval_row.current_equity)
                    if bool(eval_row.daily_dd_guard_blocking):
                        self._db.update_pending_fill_status(fill.id, "CANCELLED")
                        self._db.insert_event(
                            EventRow(
                                id=str(uuid4()),
                                eval_id=fill.eval_id,
                                ts=utc_iso(),
                                type=EventType.ORDER_CANCELLED.value,
                                payload_json=json.dumps(
                                    {
                                        "pending_fill_id": fill.id,
                                        "action": fill.action,
                                        "reason": "daily dd guard blocking",
                                    }
                                ),
                            )
                        )
                        self._db.insert_event(
                            EventRow(
                                id=str(uuid4()),
                                eval_id=fill.eval_id,
                                ts=utc_iso(),
                                type=EventType.DAILY_DD_GUARD_BLOCKED_ENTRY.value,
                                payload_json=json.dumps(
                                    {
                                        "source": "pending_fill",
                                        "pending_fill_id": fill.id,
                                        "reason": eval_row.daily_dd_guard_reason,
                                    }
                                ),
                            )
                        )
                        continue
                if fill.action == "OPEN":
                    executed = self._execute_open_from_pending(eval_row, fill)
                else:
                    executed = self._execute_close_from_pending(eval_row, fill)
                if executed:
                    self._db.update_pending_fill_status(fill.id, "EXECUTED")
            except Exception:
                self._logger.exception(
                    "pending fill processing failed eval=%s fill=%s action=%s",
                    fill.eval_id,
                    fill.id,
                    fill.action,
                )
                self._db.update_pending_fill_status(fill.id, "CANCELLED")
                self._db.insert_event(
                    EventRow(
                        id=str(uuid4()),
                        eval_id=fill.eval_id,
                        ts=utc_iso(),
                        type=EventType.ORDER_CANCELLED.value,
                        payload_json=json.dumps(
                            {
                                "pending_fill_id": fill.id,
                                "action": fill.action,
                                "reason": "executor error",
                            }
                        ),
                    )
                )

    async def _evaluate(self) -> None:
        self.update_feed_state()
        monitored_evals = self._db.list_monitored_evals()
        if not monitored_evals:
            return
        open_positions = self._db.list_open_positions()
        positions_by_eval: dict[str, list[PositionRow]] = {}
        for position in open_positions:
            positions_by_eval.setdefault(position.eval_id, []).append(position)

        for eval_row in monitored_evals:
            positions = positions_by_eval.get(eval_row.id, [])
            try:
                await self._update_eval(eval_row, positions)
            except Exception:
                self._logger.exception("eval update failed eval=%s", eval_row.id)

    async def _update_eval(self, eval_row: EvalRow, positions: list[PositionRow]) -> None:
        now = utc_now()
        eval_row = self._maybe_apply_daily_reset(eval_row, now, eval_row.current_equity)
        eval_row = self._refresh_daily_dd_guard(eval_row, eval_row.current_equity)

        unrealized = 0.0
        remaining_open_positions = len(positions)
        for position in positions:
            bar = self._price_service.get_latest_bar(position.symbol)
            if not bar:
                continue
            feed_state = self._feed_state.get(position.symbol)
            if feed_state == "STALE":
                continue
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_row.id,
                    ts=utc_iso(),
                    type=EventType.PRICE_TICK.value,
                    payload_json=json.dumps(
                        {
                            "symbol": position.symbol,
                            "bar_ts": bar.ts.isoformat(),
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                        }
                    ),
                )
            )
            position_side = Side(position.side)
            stop_hit, tp_hit = evaluate_crossing(
                position_side, position.stop_price, position.tp_price, bar.high, bar.low
            )
            decision = self._gap_resolution(position, bar.close)
            if decision:
                stop_hit, tp_hit = decision
            if stop_hit or tp_hit:
                if bool(eval_row.latency_enabled):
                    action = "CLOSE_SL" if stop_hit else "CLOSE_TP"
                    intended_price = position.stop_price if stop_hit else position.tp_price
                    self._schedule_pending_close(eval_row, position, action, intended_price)
                    continue

                exit_price = position.stop_price if stop_hit else position.tp_price
                exit_slippage = (
                    self._random_slippage(eval_row.slippage_min_usd, eval_row.slippage_max_usd)
                    if bool(eval_row.slippage_enabled)
                    else 0.0
                )
                exit_fill_price = self._apply_slippage(
                    position_side.value, exit_price, exit_slippage, is_entry=False
                )
                exit_fee = (
                    self._calculate_fee(position.qty, exit_fill_price, eval_row.taker_fee_rate)
                    if bool(eval_row.fees_enabled)
                    else 0.0
                )
                total_fees = (position.entry_fee or 0.0) + exit_fee
                pnl = self._calculate_pnl(
                    position_side,
                    position.entry_fill_price or position.entry_price,
                    exit_fill_price,
                    position.qty,
                ) - total_fees
                realized_delta = pnl + (position.entry_fee or 0.0)
                fees = total_fees
                reason = "STOP" if stop_hit else "TP"
                r_multiple_value = compute_r_multiple(
                    position.side,
                    position.entry_price,
                    position.stop_price,
                    exit_price,
                )
                r_multiple = float(r_multiple_value) if r_multiple_value is not None else None
                if r_multiple_value is None:
                    self._logger.warning(
                        "r_multiple_missing eval=%s position=%s side=%s entry=%.6f stop=%.6f exit=%.6f",
                        eval_row.id,
                        position.id,
                        position.side,
                        position.entry_price,
                        position.stop_price,
                        exit_price,
                    )
                self._db.close_position(
                    position.id,
                    utc_iso(),
                    exit_price,
                    r_multiple,
                    pnl,
                    fees,
                    exit_fee,
                    total_fees,
                    exit_slippage,
                    exit_fill_price,
                    reason,
                )
                self._logger.info(
                    "trade_closed eval=%s position=%s side=%s entry=%.6f stop=%.6f exit=%.6f r_multiple=%s pnl=%.2f",
                    eval_row.id,
                    position.id,
                    position.side,
                    position.entry_price,
                    position.stop_price,
                    exit_price,
                    f"{r_multiple:.4f}" if r_multiple is not None else "null",
                    pnl,
                )
                self._db.insert_event(
                    EventRow(
                        id=str(uuid4()),
                        eval_id=eval_row.id,
                        ts=utc_iso(),
                        type=EventType.STOP_HIT.value if stop_hit else EventType.TP_HIT.value,
                        payload_json=json.dumps(
                    {
                        "position_id": position.id,
                        "exit_price": exit_price,
                        "exit_fill_price": exit_fill_price,
                        "pnl": pnl,
                        "exit_fee": exit_fee,
                        "exit_slippage": exit_slippage,
                        "r_multiple": r_multiple,
                    }
                ),
            )
        )
                asyncio.create_task(
                    self._ws.broadcast(
                        WSMessage(
                            type="position_closed",
                            data={
                                "eval_id": eval_row.id,
                                "position_id": position.id,
                                "exit_price": exit_price,
                                "pnl": pnl,
                                "reason": reason,
                            },
                        )
                    )
                )
                eval_row = EvalRow(
                    id=eval_row.id,
                    name=eval_row.name,
                    strategy_key=eval_row.strategy_key,
                    account_type=eval_row.account_type,
                    prop_firm_mode=eval_row.prop_firm_mode,
                    symbol=eval_row.symbol,
                    rules_json=eval_row.rules_json,
                    status=eval_row.status,
                    created_at=eval_row.created_at,
                    starting_balance=eval_row.starting_balance,
                    risk_usd=eval_row.risk_usd,
                    current_balance=eval_row.current_balance + realized_delta,
                    current_equity=eval_row.current_equity + realized_delta,
                    day_start_equity=eval_row.day_start_equity,
                    day_window_start_ts=eval_row.day_window_start_ts,
                    last_daily_reset_day=eval_row.last_daily_reset_day,
                    max_dd_pct=eval_row.max_dd_pct,
                    daily_dd_pct=eval_row.daily_dd_pct,
                    fees_enabled=eval_row.fees_enabled,
                    slippage_enabled=eval_row.slippage_enabled,
                    taker_fee_rate=eval_row.taker_fee_rate,
                    slippage_min_usd=eval_row.slippage_min_usd,
                    slippage_max_usd=eval_row.slippage_max_usd,
                    risk_updated_at=eval_row.risk_updated_at,
                    profit_target_pct=eval_row.profit_target_pct,
                    passed_at=eval_row.passed_at,
                    archived_at=eval_row.archived_at,
                    stats_cache_json=eval_row.stats_cache_json,
                    fail_reason=eval_row.fail_reason,
                    max_dd_used_pct=eval_row.max_dd_used_pct,
                    worst_daily_dd_used_pct=eval_row.worst_daily_dd_used_pct,
                    latency_enabled=eval_row.latency_enabled,
                    latency_min_sec=eval_row.latency_min_sec,
                    latency_max_sec=eval_row.latency_max_sec,
                    dynamic_tp_enabled=eval_row.dynamic_tp_enabled,
                    webhook_passthrough_enabled=eval_row.webhook_passthrough_enabled,
                    webhook_passthrough_url=eval_row.webhook_passthrough_url,
                    daily_dd_guard_enabled=eval_row.daily_dd_guard_enabled,
                    daily_dd_guard_risk_multiple=eval_row.daily_dd_guard_risk_multiple,
                    daily_dd_guard_buffer_pct=eval_row.daily_dd_guard_buffer_pct,
                    daily_dd_guard_buffer_usd=eval_row.daily_dd_guard_buffer_usd,
                    daily_dd_guard_auto_resume_on_daily_reset=eval_row.daily_dd_guard_auto_resume_on_daily_reset,
                    daily_dd_guard_close_open_positions_on_trigger=eval_row.daily_dd_guard_close_open_positions_on_trigger,
                    daily_dd_guard_blocking=eval_row.daily_dd_guard_blocking,
                    daily_dd_guard_blocked_at=eval_row.daily_dd_guard_blocked_at,
                    daily_dd_guard_reason=eval_row.daily_dd_guard_reason,
                )
                remaining_open_positions = max(0, remaining_open_positions - 1)
            else:
                unrealized += self._calculate_pnl(
                    position_side,
                    position.entry_fill_price or position.entry_price,
                    bar.close,
                    position.qty,
                )
                self._db.update_position_check(position.id, utc_iso(), bar.close)

        current_equity = eval_row.current_balance + unrealized
        eval_row = self._refresh_daily_dd_guard(eval_row, current_equity)
        day_start_equity = eval_row.day_start_equity

        max_used_pct = max(0.0, (eval_row.starting_balance - current_equity) / eval_row.starting_balance)
        daily_used_pct = max(0.0, (day_start_equity - current_equity) / day_start_equity)
        worst_max = max(eval_row.max_dd_used_pct or 0.0, max_used_pct)
        worst_daily = max(eval_row.worst_daily_dd_used_pct or 0.0, daily_used_pct)
        self._db.update_eval_dd_stats(eval_row.id, worst_max, worst_daily)
        self._db.insert_equity_point(
            EquityPointRow(
                eval_id=eval_row.id,
                ts=utc_iso(),
                equity=current_equity,
                drawdown_pct=max_used_pct,
                daily_dd_limit_equity=day_start_equity * (1 - eval_row.daily_dd_pct),
                max_dd_limit_equity=eval_row.starting_balance * (1 - eval_row.max_dd_pct),
            )
        )
        failed = False
        fail_reason = None
        passed = False
        if current_equity <= eval_row.starting_balance * (1 - eval_row.max_dd_pct):
            failed = True
            fail_reason = "FAIL_MAX_DD"
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_row.id,
                    ts=utc_iso(),
                    type=EventType.EVAL_FAILED.value,
                    payload_json=json.dumps({"reason": "max drawdown breached"}),
                )
            )
        if current_equity <= day_start_equity * (1 - eval_row.daily_dd_pct):
            failed = True
            if fail_reason is None:
                fail_reason = "FAIL_DAILY_DD"
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=eval_row.id,
                    ts=utc_iso(),
                    type=EventType.EVAL_FAILED.value,
                    payload_json=json.dumps({"reason": "daily drawdown breached"}),
                )
            )

        target_pct = normalize_profit_target_pct(eval_row.profit_target_pct)
        if not failed and target_pct is not None and remaining_open_positions == 0:
            target_equity = eval_row.starting_balance * (1 + target_pct)
            if current_equity >= target_equity:
                passed = True
                self._db.insert_event(
                    EventRow(
                        id=str(uuid4()),
                        eval_id=eval_row.id,
                        ts=utc_iso(),
                        type=EventType.EVAL_PASSED.value,
                        payload_json=json.dumps({"reason": "profit target reached"}),
                    )
                )

        status = EvalStatus.FAILED.value if failed else EvalStatus.PASSED.value if passed else None
        self._db.update_eval_financials(
            eval_row.id,
            eval_row.current_balance,
            current_equity,
            day_start_equity,
            eval_row.day_window_start_ts,
            status,
            utc_iso() if passed else None,
        )
        if failed and fail_reason:
            self._db.update_eval_failure(eval_row.id, EvalStatus.FAILED.value, fail_reason)
            self._cancel_pending_fills(eval_row.id, "eval failed")
        if passed:
            self._cancel_pending_fills(eval_row.id, "eval passed")
        updated = self._db.fetch_eval(eval_row.id)
        if updated:
            closed_positions = self._db.list_closed_positions_for_eval(updated.id)
            rolling_positions = self._db.list_closed_positions_for_eval_limit(updated.id, 20)
            summary = summarize_eval(updated, closed_positions, rolling_positions)
            if updated.status in (EvalStatus.PASSED.value, EvalStatus.FAILED.value):
                self._record_strategy_run(updated, closed_positions, summary, fail_reason)
            asyncio.create_task(
                self._ws.broadcast(
                    WSMessage(
                        type="eval_update",
                        data={
                            "eval_id": updated.id,
                            "current_balance": updated.current_balance,
                            "current_equity": updated.current_equity,
                            "status": updated.status,
                            "day_start_equity": updated.day_start_equity,
                            "day_window_start_ts": updated.day_window_start_ts,
                            "profit_target_pct": updated.profit_target_pct,
                            "profit_target_equity": summary.get("profit_target_equity"),
                            "profit_remaining_usd": summary.get("profit_remaining_usd"),
                            "profit_progress_pct": summary.get("profit_progress_pct"),
                            "wins": summary.get("wins"),
                            "losses": summary.get("losses"),
                            "breakeven": summary.get("breakeven"),
                            "win_rate_pct": summary.get("win_rate_pct"),
                            "profit_factor": summary.get("profit_factor"),
                            "rolling_net_pnl": summary.get("rolling_net_pnl"),
                            "rolling_avg_pnl_per_trade": summary.get("rolling_avg_pnl_per_trade"),
                            "rolling_win_rate": summary.get("rolling_win_rate"),
                            "rolling_profit_factor": summary.get("rolling_profit_factor"),
                            "expected_trades_to_pass": summary.get("expected_trades_to_pass"),
                            "expected_days_to_pass": summary.get("expected_days_to_pass"),
                            "expected_trades_to_daily_fail": summary.get("expected_trades_to_daily_fail"),
                            "expected_trades_to_max_fail": summary.get("expected_trades_to_max_fail"),
                            "daily_dd_guard_blocking": bool(updated.daily_dd_guard_blocking),
                            "daily_dd_guard_reason": updated.daily_dd_guard_reason,
                        },
                    )
                )
            )

    def update_feed_state(self) -> None:
        ticks = self._price_service.get_latest_ticks()
        now = datetime.now(timezone.utc)
        for symbol in ("BTC", "ETH", "SOL"):
            tick = ticks.get(symbol)
            if not tick:
                self._set_feed_state(symbol, "STALE", None)
                continue
            age = (now - tick.ts).total_seconds()
            state = "FRESH" if age <= self._stale_after_seconds else "STALE"
            self._set_feed_state(symbol, state, tick.ts)

    def _set_feed_state(self, symbol: str, state: str, ts: Optional[datetime]) -> None:
        prev = self._feed_state.get(symbol)
        if prev == state:
            return
        self._feed_state[symbol] = state
        event_type = EventType.PRICE_FEED_RESUMED if state == "FRESH" else EventType.PRICE_FEED_STALE
        for row in self._db.list_monitored_evals():
            if row.symbol != symbol:
                continue
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=row.id,
                    ts=utc_iso(),
                    type=event_type.value,
                    payload_json=json.dumps(
                        {"symbol": symbol, "state": state, "last_price_ts": ts.isoformat() if ts else None}
                    ),
                )
            )

    def _daily_dd_guard_threshold_usd(self, eval_row: EvalRow) -> float:
        return max(
            0.0,
            (
                eval_row.risk_usd * float(eval_row.daily_dd_guard_risk_multiple or 0.0)
                + eval_row.risk_usd * float(eval_row.daily_dd_guard_buffer_pct or 0.0)
                + float(eval_row.daily_dd_guard_buffer_usd or 0.0)
            ),
        )

    def _daily_dd_remaining_usd(self, eval_row: EvalRow, current_equity: float) -> float:
        daily_floor = eval_row.day_start_equity * (1 - eval_row.daily_dd_pct)
        return max(0.0, current_equity - daily_floor)

    def _refresh_daily_dd_guard(self, eval_row: EvalRow, current_equity: float) -> EvalRow:
        enabled = bool(eval_row.daily_dd_guard_enabled)
        was_blocking = bool(eval_row.daily_dd_guard_blocking)
        if not enabled:
            if was_blocking:
                self._db.update_eval_daily_dd_guard_state(eval_row.id, 0, None, None)
                refreshed = self._db.fetch_eval(eval_row.id)
                return refreshed or eval_row
            return eval_row

        threshold = self._daily_dd_guard_threshold_usd(eval_row)
        remaining = self._daily_dd_remaining_usd(eval_row, current_equity)
        should_block = remaining <= threshold
        if was_blocking and not should_block and not bool(eval_row.daily_dd_guard_auto_resume_on_daily_reset):
            should_block = True
        if should_block == was_blocking:
            return eval_row

        reason = None
        event_type = EventType.DAILY_DD_GUARD_RELEASED.value
        blocked_at = None
        if should_block:
            reason = (
                f"daily DD protection: remaining ${remaining:.2f} <= threshold ${threshold:.2f}"
            )
            blocked_at = utc_iso()
            event_type = EventType.DAILY_DD_GUARD_ACTIVATED.value

        self._db.update_eval_daily_dd_guard_state(
            eval_row.id,
            1 if should_block else 0,
            blocked_at if should_block else None,
            reason,
        )
        self._db.insert_event(
            EventRow(
                id=str(uuid4()),
                eval_id=eval_row.id,
                ts=utc_iso(),
                type=event_type,
                payload_json=json.dumps(
                    {
                        "current_equity": current_equity,
                        "day_start_equity": eval_row.day_start_equity,
                        "daily_remaining_usd": remaining,
                        "threshold_usd": threshold,
                        "risk_usd": eval_row.risk_usd,
                        "risk_multiple": eval_row.daily_dd_guard_risk_multiple,
                        "buffer_pct": eval_row.daily_dd_guard_buffer_pct,
                        "buffer_usd": eval_row.daily_dd_guard_buffer_usd,
                    }
                ),
            )
        )
        if should_block and bool(eval_row.daily_dd_guard_close_open_positions_on_trigger):
            self._exit_all_for_eval(eval_row)
        refreshed = self._db.fetch_eval(eval_row.id)
        return refreshed or eval_row

    def _record_strategy_run(
        self,
        row: EvalRow,
        closed_positions: list[PositionRow],
        summary: dict[str, Optional[float]],
        fail_reason: Optional[str],
    ) -> None:
        if self._db.strategy_run_exists(row.id):
            return
        ruleset = build_ruleset(row)
        rules_hash = ruleset_hash(ruleset)
        family, version = derive_strategy_family(row.strategy_key)
        trades_count = len(closed_positions)
        fees_paid = sum((position.total_fees or 0.0) for position in closed_positions)
        slippage_impact = sum(
            ((position.entry_slippage or 0.0) + (position.exit_slippage or 0.0)) * position.qty
            for position in closed_positions
        )
        win_rate = summary.get("win_rate_pct")
        win_rate_value = (win_rate / 100) if win_rate is not None else None
        result = row.status
        ended_at = row.passed_at or utc_iso()
        self._db.insert_strategy_run(
            {
                "id": str(uuid4()),
                "eval_id": row.id,
                "strategy_key": row.strategy_key,
                "strategy_family": family,
                "strategy_version": version,
                "symbol": row.symbol,
                "ruleset_json": json.dumps(ruleset, sort_keys=True),
                "ruleset_hash": rules_hash,
                "started_at": row.created_at,
                "ended_at": ended_at,
                "result": result,
                "fail_reason": row.fail_reason or fail_reason,
                "starting_balance": row.starting_balance,
                "ending_equity": row.current_equity,
                "net_pnl": row.current_equity - row.starting_balance,
                "trades_count": trades_count,
                "wins": summary.get("wins") or 0,
                "losses": summary.get("losses") or 0,
                "win_rate": win_rate_value,
                "profit_factor": summary.get("profit_factor"),
                "max_dd_used_pct": row.max_dd_used_pct,
                "worst_daily_dd_used_pct": row.worst_daily_dd_used_pct,
                "fees_paid": fees_paid,
                "slippage_impact": slippage_impact,
                "notes": None,
            }
        )

    def _signal_dedupe_key(
        self,
        strategy_key: str,
        symbol: str,
        payload: TradingViewPayload,
        received_at: str,
    ) -> str:
        if payload.signal_id:
            return payload.signal_id
        base = (
            f"{strategy_key}|{symbol}|{payload.side.value}|{payload.entry}|"
            f"{payload.stop}|{payload.tp}|{received_at[:16]}"
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def _gap_resolution(self, position: PositionRow, current_price: float) -> Optional[tuple[bool, bool]]:
        if not position.last_checked_ts or position.last_checked_price is None:
            return None
        from_price = position.last_checked_price
        to_price = current_price
        low = min(from_price, to_price)
        high = max(from_price, to_price)
        stop_hit = tp_hit = False
        if position.tp_price is None:
            if position.side == Side.LONG.value:
                stop_hit = low <= position.stop_price
            else:
                stop_hit = high >= position.stop_price
            if stop_hit:
                self._db.insert_event(
                    EventRow(
                        id=str(uuid4()),
                        eval_id=position.eval_id,
                        ts=utc_iso(),
                        type=EventType.GAP_RESOLUTION.value,
                        payload_json=json.dumps(
                            {
                                "from_ts": position.last_checked_ts,
                                "to_ts": utc_iso(),
                                "from_price": from_price,
                                "to_price": to_price,
                                "decision": "STOP",
                            }
                        ),
                    )
                )
            return stop_hit, False
        if position.side == Side.LONG.value:
            stop_hit = low <= position.stop_price
            tp_hit = high >= position.tp_price
        else:
            stop_hit = high >= position.stop_price
            tp_hit = low <= position.tp_price
        if stop_hit and tp_hit:
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=position.eval_id,
                    ts=utc_iso(),
                    type=EventType.GAP_RESOLUTION.value,
                    payload_json=json.dumps(
                        {
                            "from_ts": position.last_checked_ts,
                            "to_ts": utc_iso(),
                            "from_price": from_price,
                            "to_price": to_price,
                            "decision": "STOP",
                        }
                    ),
                )
            )
            return True, False
        if stop_hit or tp_hit:
            self._db.insert_event(
                EventRow(
                    id=str(uuid4()),
                    eval_id=position.eval_id,
                    ts=utc_iso(),
                    type=EventType.GAP_RESOLUTION.value,
                    payload_json=json.dumps(
                        {
                            "from_ts": position.last_checked_ts,
                            "to_ts": utc_iso(),
                            "from_price": from_price,
                            "to_price": to_price,
                            "decision": "STOP" if stop_hit else "TP",
                        }
                    ),
                )
            )
        return stop_hit, tp_hit

    @staticmethod
    def _calculate_pnl(side: Side, entry: float, exit_price: float, qty: float) -> float:
        if side == Side.LONG:
            return (exit_price - entry) * qty
        return (entry - exit_price) * qty

    @staticmethod
    def _calculate_qty(risk_usd: float, entry: float, stop: float) -> Optional[float]:
        distance = abs(entry - stop)
        if distance <= 0:
            return None
        return risk_usd / distance

    @staticmethod
    def _calculate_fee(qty: float, price: float, fee_rate: float) -> float:
        return qty * price * fee_rate

    @staticmethod
    def _apply_slippage(side: str, price: float, slippage: float, is_entry: bool) -> float:
        if side == Side.LONG.value:
            return price + slippage if is_entry else price - slippage
        return price - slippage if is_entry else price + slippage

    @staticmethod
    def _random_slippage(min_usd: float, max_usd: float) -> float:
        if max_usd <= min_usd:
            return min_usd
        return random.uniform(min_usd, max_usd)


def validate_trade_signal(
    side: str,
    entry_price: Optional[float],
    stop_price: Optional[float],
    tp_price: Optional[float],
    dynamic_tp_enabled: bool = False,
) -> tuple[bool, str]:
    if entry_price is None:
        return False, "missing entry for validation"
    if stop_price is None:
        return False, "missing stop"
    if not all(math.isfinite(value) for value in (entry_price, stop_price)):
        return False, "stop is not a finite number"
    if dynamic_tp_enabled:
        if side == Side.LONG.value:
            if stop_price >= entry_price:
                return False, "stop must be below entry for LONG"
        if side == Side.SHORT.value:
            if stop_price <= entry_price:
                return False, "stop must be above entry for SHORT"
        if side not in (Side.LONG.value, Side.SHORT.value):
            return False, "invalid side"
        return True, "ok"
    if tp_price is None:
        return False, "missing take profit"
    if not math.isfinite(tp_price):
        return False, "take profit is not a finite number"
    if stop_price == tp_price:
        return False, "stop equals take profit"
    if side == Side.LONG.value:
        if stop_price >= entry_price:
            return False, "stop must be below entry for LONG"
        if tp_price <= entry_price:
            return False, "tp must be above entry for LONG"
    if side == Side.SHORT.value:
        if stop_price <= entry_price:
            return False, "stop must be above entry for SHORT"
        if tp_price >= entry_price:
            return False, "tp must be below entry for SHORT"
    if side not in (Side.LONG.value, Side.SHORT.value):
        return False, "invalid side"
    return True, "ok"


def resolve_symbol_from_ticker(ticker: str) -> Optional[str]:
    return map_ticker_to_symbol(ticker)
