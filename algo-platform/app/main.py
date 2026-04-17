from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import statistics
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any, Optional

from fastapi import FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .db import Database, StrategyRow
from .eval_manager import EvalManager
from .instruments import (
    is_supported_instrument,
    matches_instrument_ticker,
    resolve_instrument_from_ticker,
)
from .market_data_matrix import MARKET_DATA_MATRIX
from .models import (
    EvalCreateRequest,
    EvalCostUpdateRequest,
    EvalEventResponse,
    EvalLatencyUpdateRequest,
    EquityPointResponse,
    EvalRiskUpdateRequest,
    EvalProfitTargetRequest,
    EvalDynamicTPUpdateRequest,
    EvalDailyDDGuardUpdateRequest,
    EvalWebhookPassthroughUpdateRequest,
    EvalResponse,
    FailureResponse,
    HealthResponse,
    MarketDataMatrixRowResponse,
    PriceTickResponse,
    PositionResponse,
    StrategyCreateRequest,
    StrategyResponse,
    StrategyUpdateRequest,
    SuccessResponse,
    TradeResponse,
    TradingViewPayload,
)
from .price_service import PriceService
from .realtime import WebSocketManager
from .registry import STRATEGY_REGISTRY, StrategyConfig, default_handler
from .utils import ensure_aware, next_et_midnight, validate_payload
from .analytics import (
    summarize_eval,
    normalize_profit_target_pct,
    derive_strategy_family,
    build_ruleset,
    ruleset_hash,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

app = FastAPI()
db_path = os.getenv("DB_PATH", os.path.join(os.getcwd(), "simulator.db"))
db = Database(db_path)
ws_manager = WebSocketManager()
price_service = PriceService(db, ws_manager)
eval_manager = EvalManager(db, price_service, ws_manager)
last_wal_checkpoint_at: Optional[str] = None


def _failure(reason: str, status_code: int = 400) -> JSONResponse:
    payload = FailureResponse(reason=reason)
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


def _format_validation_error(error: ValidationError) -> str:
    parts = []
    for detail in error.errors():
        loc = ".".join(str(item) for item in detail.get("loc", []))
        msg = detail.get("msg", "invalid")
        parts.append(f"{loc}: {msg}".strip())
    return "Invalid payload: " + "; ".join(parts)


def _get_strategy_config(strategy_key: str) -> Optional[StrategyConfig]:
    return STRATEGY_REGISTRY.get(strategy_key)


def _normalize_account_type(
    account_type: str,
    prop_firm_mode: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    normalized_type = (account_type or "").strip().upper()
    normalized_mode = (prop_firm_mode or "").strip().upper() or None
    if normalized_type not in {"REGULAR", "PROP_FIRM"}:
        return None, None, "Account type must be REGULAR or PROP_FIRM"
    if normalized_type == "REGULAR":
        return normalized_type, None, None
    if normalized_mode not in {"EVAL", "LIVE_SIM"}:
        return None, None, "Prop firm accounts require mode EVAL or LIVE_SIM"
    return normalized_type, normalized_mode, None


def _strategy_response(row: StrategyRow) -> StrategyResponse:
    return StrategyResponse(
        key=row.key,
        name=row.name,
        symbol=row.symbol,
        created_at=row.created_at,
        updated_at=row.updated_at,
        webhook_passthrough_enabled=bool(row.webhook_passthrough_enabled),
        webhook_passthrough_url=row.webhook_passthrough_url,
    )


def _is_exit_all_payload(raw_payload: Any) -> bool:
    if not isinstance(raw_payload, dict):
        return False
    exit_value = raw_payload.get("exit")
    if exit_value is True:
        return True
    if isinstance(exit_value, str) and exit_value.lower() == "all":
        return True
    action = raw_payload.get("action")
    if isinstance(action, str) and action.lower() == "exit":
        return True
    payload_type = raw_payload.get("type")
    if isinstance(payload_type, str) and payload_type.lower() == "exit":
        return True
    return False


def _process_webhook(
    strategy_key: str,
    raw_payload: Any,
    raw_body: bytes,
    content_type: Optional[str],
) -> JSONResponse:
    if not strategy_key:
        return _failure("Missing strategy key", status_code=400)
    if not db.fetch_strategy(strategy_key):
        return _failure("Strategy not found", status_code=404)

    _forward_webhook_passthrough(strategy_key, raw_body, content_type)

    if _is_exit_all_payload(raw_payload):
        matched = eval_manager.exit_all_positions(strategy_key)
        if matched == 0:
            return _failure("No evals matched", status_code=404)
        response = SuccessResponse(event_id=eval_manager_id(), strategy_key=strategy_key)
        return JSONResponse(status_code=200, content=jsonable_encoder(response))

    config = _get_strategy_config(strategy_key)

    try:
        payload = TradingViewPayload.model_validate(raw_payload)
    except ValidationError as exc:
        return _failure(_format_validation_error(exc), status_code=400)

    try:
        validate_payload(payload)
    except ValueError as exc:
        return _failure(str(exc), status_code=400)

    strategy = db.fetch_strategy(strategy_key)
    if not strategy:
        return _failure("Strategy not found", status_code=404)

    symbol = strategy.symbol
    if not matches_instrument_ticker(symbol, payload.ticker):
        resolved = resolve_instrument_from_ticker(payload.ticker)
        if resolved is None:
            return _failure("Unsupported ticker for configured strategy instrument", status_code=400)
        return _failure(
            f"Ticker routes to {resolved}, but strategy is configured for {symbol}",
            status_code=400,
        )

    logger.info(
        "signal | %s | %s | %s | %s | %s | %s",
        strategy_key,
        symbol,
        payload.side,
        payload.entry,
        payload.stop,
        payload.tp,
    )

    handler = config.handler if config else default_handler
    matched = handler(eval_manager, strategy_key, symbol, payload)
    if matched == 0:
        return _failure("No active evals matched", status_code=404)

    response = SuccessResponse(event_id=eval_manager_id(), strategy_key=strategy_key)
    return JSONResponse(status_code=200, content=jsonable_encoder(response))


@app.post("/api/webhook/{strategy_key}")
async def webhook_with_key(
    strategy_key: str,
    request: Request,
) -> JSONResponse:
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return _failure("Invalid payload: malformed JSON", status_code=400)
    return _process_webhook(strategy_key, payload, raw_body, request.headers.get("content-type"))


@app.post("/api/webhook")
async def webhook_header_key(
    request: Request,
    x_strategy_key: Optional[str] = Header(None, alias="X-Strategy-Key"),
) -> JSONResponse:
    if not x_strategy_key:
        return _failure("Missing X-Strategy-Key header", status_code=400)
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return _failure("Invalid payload: malformed JSON", status_code=400)
    return _process_webhook(x_strategy_key, payload, raw_body, request.headers.get("content-type"))


@app.get("/api/strategies", response_model=list[StrategyResponse])
async def list_strategies() -> list[StrategyResponse]:
    rows = db.list_strategies()
    return [_strategy_response(row) for row in rows]


@app.post("/api/strategies", response_model=StrategyResponse)
async def create_strategy(request: StrategyCreateRequest) -> JSONResponse | StrategyResponse:
    key = request.key.strip()
    name = request.name.strip()
    symbol = request.symbol.strip().upper()
    if not key:
        return _failure("Strategy key is required", status_code=400)
    if not name:
        return _failure("Strategy name is required", status_code=400)
    if not is_supported_instrument(symbol):
        return _failure("Unsupported instrument", status_code=400)
    if db.fetch_strategy(key):
        return _failure("Strategy key already exists", status_code=409)
    enabled, url, error = _normalize_webhook_passthrough_settings(
        request.webhook_passthrough_enabled,
        request.webhook_passthrough_url,
    )
    if error:
        return _failure(error, status_code=400)
    now = datetime.now(timezone.utc).isoformat()
    row = StrategyRow(
        key=key,
        name=name,
        symbol=symbol,
        created_at=now,
        updated_at=now,
        webhook_passthrough_enabled=1 if enabled else 0,
        webhook_passthrough_url=url,
    )
    db.insert_strategy(row)
    return _strategy_response(row)


@app.post("/api/strategies/{strategy_key}", response_model=StrategyResponse)
async def update_strategy(
    strategy_key: str,
    request: StrategyUpdateRequest,
) -> JSONResponse | StrategyResponse:
    row = db.fetch_strategy(strategy_key)
    if not row:
        return _failure("Strategy not found", status_code=404)
    name = request.name.strip()
    symbol = request.symbol.strip().upper()
    if not name:
        return _failure("Strategy name is required", status_code=400)
    if not is_supported_instrument(symbol):
        return _failure("Unsupported instrument", status_code=400)
    enabled, url, error = _normalize_webhook_passthrough_settings(
        request.webhook_passthrough_enabled,
        request.webhook_passthrough_url,
    )
    if error:
        return _failure(error, status_code=400)
    updated_at = datetime.now(timezone.utc).isoformat()
    db.update_strategy(
        strategy_key,
        name,
        symbol,
        1 if enabled else 0,
        url,
        updated_at,
    )
    updated = db.fetch_strategy(strategy_key)
    if not updated:
        return _failure("Strategy not found", status_code=404)
    return _strategy_response(updated)


@app.post("/api/evals", response_model=EvalResponse)
async def create_eval(request: EvalCreateRequest) -> EvalResponse:
    strategy = db.fetch_strategy(request.strategy_key)
    if not strategy:
        return _failure("Strategy not found", status_code=404)
    if not is_supported_instrument(strategy.symbol):
        return _failure("Strategy ticker is not configured", status_code=400)
    account_type, prop_firm_mode, account_error = _normalize_account_type(
        request.account_type,
        request.prop_firm_mode,
    )
    if account_error:
        return _failure(account_error, status_code=400)
    row = eval_manager.create_eval(
        name=request.name,
        strategy_key=request.strategy_key,
        account_type=account_type,
        prop_firm_mode=prop_firm_mode,
        symbol=strategy.symbol,
        starting_balance=request.starting_balance,
        risk_usd=request.risk_usd,
        fees_enabled=request.fees_enabled,
        slippage_enabled=request.slippage_enabled,
        taker_fee_rate=request.taker_fee_rate,
        slippage_min_usd=request.slippage_min_usd,
        slippage_max_usd=request.slippage_max_usd,
        max_dd_pct=request.max_dd_pct,
        daily_dd_pct=request.daily_dd_pct,
        profit_target_pct=normalize_profit_target_pct(request.profit_target_pct),
        latency_enabled=request.latency_enabled,
        latency_min_sec=request.latency_min_sec,
        latency_max_sec=request.latency_max_sec,
        dynamic_tp_enabled=request.dynamic_tp_enabled,
        webhook_passthrough_enabled=bool(strategy.webhook_passthrough_enabled),
        webhook_passthrough_url=strategy.webhook_passthrough_url,
    )
    return _eval_response(row)


@app.get("/api/evals", response_model=list[EvalResponse])
async def list_evals(status: Optional[str] = None, view: Optional[str] = None) -> list[EvalResponse]:
    rows = db.list_evals_filtered(status, view)
    return [_eval_response(row) for row in rows]


@app.get("/api/evals/{eval_id}", response_model=EvalResponse)
async def get_eval(eval_id: str) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    return _eval_response(row)


@app.post("/api/evals/{eval_id}/pause", response_model=EvalResponse)
async def pause_eval(eval_id: str) -> JSONResponse | EvalResponse:
    row = eval_manager.pause_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    return _eval_response(row)


@app.post("/api/evals/{eval_id}/resume", response_model=EvalResponse)
async def resume_eval(eval_id: str) -> JSONResponse | EvalResponse:
    row = eval_manager.resume_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    return _eval_response(row)


@app.post("/api/evals/{eval_id}/risk", response_model=EvalResponse)
async def update_eval_risk(eval_id: str, request: EvalRiskUpdateRequest) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    db.update_eval_risk(eval_id, request.risk_usd, datetime.now(timezone.utc).isoformat())
    return _eval_response(db.fetch_eval(eval_id))


@app.post("/api/evals/{eval_id}/settings", response_model=EvalResponse)
async def update_eval_settings(
    eval_id: str, request: EvalCostUpdateRequest
) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    db.update_eval_costs(
        eval_id,
        1 if request.fees_enabled else 0,
        1 if request.slippage_enabled else 0,
        request.taker_fee_rate,
        request.slippage_min_usd,
        request.slippage_max_usd,
    )
    return _eval_response(db.fetch_eval(eval_id))


@app.post("/api/evals/{eval_id}/latency", response_model=EvalResponse)
async def update_eval_latency(
    eval_id: str, request: EvalLatencyUpdateRequest
) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    db.update_eval_latency(
        eval_id,
        1 if request.latency_enabled else 0,
        request.latency_min_sec,
        request.latency_max_sec,
    )
    return _eval_response(db.fetch_eval(eval_id))


@app.post("/api/evals/{eval_id}/profit-target", response_model=EvalResponse)
async def update_profit_target(
    eval_id: str, request: EvalProfitTargetRequest
) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    db.update_eval_profit_target(eval_id, normalize_profit_target_pct(request.profit_target_pct))
    return _eval_response(db.fetch_eval(eval_id))


@app.post("/api/evals/{eval_id}/dynamic-tp", response_model=EvalResponse)
async def update_dynamic_tp(
    eval_id: str, request: EvalDynamicTPUpdateRequest
) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    db.update_eval_dynamic_tp(eval_id, 1 if request.dynamic_tp_enabled else 0)
    return _eval_response(db.fetch_eval(eval_id))


@app.post("/api/evals/{eval_id}/daily-dd-guard", response_model=EvalResponse)
async def update_daily_dd_guard(
    eval_id: str, request: EvalDailyDDGuardUpdateRequest
) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    db.update_eval_daily_dd_guard(
        eval_id,
        1 if request.enabled else 0,
        request.risk_multiple,
        request.buffer_pct,
        request.buffer_usd,
        1 if request.auto_resume_on_daily_reset else 0,
        1 if request.close_open_positions_on_trigger else 0,
    )
    return _eval_response(db.fetch_eval(eval_id))


@app.post("/api/evals/{eval_id}/webhook-passthrough", response_model=EvalResponse)
async def update_webhook_passthrough(
    eval_id: str, request: EvalWebhookPassthroughUpdateRequest
) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    strategy = db.fetch_strategy(row.strategy_key)
    if not strategy:
        return _failure("Strategy not found", status_code=404)
    enabled, url, error = _normalize_webhook_passthrough_settings(request.enabled, request.url)
    if error:
        return _failure(error, status_code=400)
    db.update_strategy(
        strategy.key,
        strategy.name,
        strategy.symbol,
        1 if enabled else 0,
        url,
        datetime.now(timezone.utc).isoformat(),
    )
    return _eval_response(db.fetch_eval(eval_id))


@app.get("/api/evals/{eval_id}/events", response_model=list[EvalEventResponse])
async def get_events(eval_id: str, limit: int = Query(50, ge=1, le=500)) -> list[EvalEventResponse]:
    rows = db.list_events(eval_id, limit)
    return [
        EvalEventResponse(
            id=row.id,
            eval_id=row.eval_id,
            ts=row.ts,
            type=row.type,
            payload=jsonable_encoder(json.loads(row.payload_json)),
        )
        for row in rows
    ]


@app.get("/api/evals/{eval_id}/equity-series", response_model=list[EquityPointResponse])
async def get_equity_series(
    eval_id: str, limit: int = Query(500, ge=10, le=5000)
) -> list[EquityPointResponse]:
    rows = db.list_equity_series(eval_id, limit)
    return [
        EquityPointResponse(
            ts=row.ts,
            equity=row.equity,
            drawdown_pct=row.drawdown_pct,
            daily_dd_limit_equity=row.daily_dd_limit_equity,
            max_dd_limit_equity=row.max_dd_limit_equity,
        )
        for row in rows
    ]


@app.delete("/api/evals/{eval_id}")
async def delete_eval(eval_id: str) -> JSONResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    db.delete_eval(eval_id)
    return JSONResponse(status_code=200, content={"deleted": True, "eval_id": eval_id})


@app.post("/api/evals/{eval_id}/archive", response_model=EvalResponse)
async def archive_eval(eval_id: str) -> JSONResponse | EvalResponse:
    row = db.fetch_eval(eval_id)
    if not row:
        return _failure("Eval not found", status_code=404)
    db.archive_eval(eval_id, datetime.now(timezone.utc).isoformat())
    archived = db.fetch_eval(eval_id)
    if archived and not db.strategy_run_exists(eval_id):
        closed_positions = db.list_closed_positions_for_eval(eval_id)
        summary = summarize_eval(archived, closed_positions, closed_positions[:20])
        _insert_strategy_run(archived, closed_positions, summary, result="STOPPED", fail_reason="MANUAL_STOP")
    return _eval_response(db.fetch_eval(eval_id))


@app.get("/api/evals/{eval_id}/trades", response_model=list[TradeResponse])
async def get_trades(eval_id: str) -> list[TradeResponse]:
    rows = db.list_closed_positions_for_eval(eval_id)
    return [
        TradeResponse(
            id=row.id,
            eval_id=row.eval_id,
            side=row.side,
            qty=row.qty,
            entry_price=row.entry_price,
            exit_price=row.exit_price,
            pnl=row.pnl,
            opened_at=row.opened_at,
            closed_at=row.closed_at,
            status=row.status,
            reason=row.reason or _exit_reason(row.exit_price, row.stop_price, row.tp_price),
            r_multiple=row.r_multiple,
            tp_disabled=bool(row.tp_disabled),
            entry_fee=row.entry_fee,
            exit_fee=row.exit_fee,
            total_fees=row.total_fees,
            entry_slippage=row.entry_slippage,
            exit_slippage=row.exit_slippage,
            entry_fill_price=row.entry_fill_price,
            exit_fill_price=row.exit_fill_price,
        )
        for row in rows
    ]


@app.get("/api/prices", response_model=dict[str, PriceTickResponse])
async def get_prices() -> dict[str, PriceTickResponse]:
    ticks = price_service.get_latest_ticks()
    if not ticks:
        cached: dict[str, PriceTickResponse] = {}
        for symbol in ("BTC", "ETH", "SOL"):
            row = db.fetch_latest_price(symbol, price_service.timeframe)
            if row:
                cached[symbol] = PriceTickResponse(
                    ts=row.ts,
                    price=row.close,
                    source=row.source,
                )
        return cached
    return {
        symbol: PriceTickResponse(ts=tick.ts.isoformat(), price=tick.price, source=tick.source)
        for symbol, tick in ticks.items()
    }


@app.get("/api/market-data/matrix", response_model=list[MarketDataMatrixRowResponse])
async def get_market_data_matrix() -> list[MarketDataMatrixRowResponse]:
    feed, ages = price_service.get_health()
    ticks = await get_prices()
    rows: list[MarketDataMatrixRowResponse] = []
    for item in MARKET_DATA_MATRIX:
        tick = ticks.get(item.instrument_id)
        rows.append(
            MarketDataMatrixRowResponse(
                instrument_id=item.instrument_id,
                display_name=item.display_name,
                asset_class=item.asset_class,
                market=item.market,
                exchange=item.exchange,
                provider=item.provider,
                provider_type=item.provider_type,
                external_ticker=item.external_ticker,
                stream_status=item.stream_status if item.instrument_id not in ticks else "live_now",
                cadence_target=item.cadence_target,
                free_access=item.free_access,
                current_price=tick.price if tick else None,
                price_ts=tick.ts if tick else None,
                price_source=tick.source if tick else (feed if item.instrument_id in ages else None),
                update_age_ms=ages.get(item.instrument_id),
                notes=item.notes,
            )
        )
    return rows


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    feed, ages = price_service.get_health()
    return HealthResponse(price_feed=feed, last_price_update_age_ms=ages)


@app.get("/health", response_model=HealthResponse)
async def health_root() -> HealthResponse:
    return await health()


@app.get("/api/strategies/summary")
async def strategy_summary() -> list[dict[str, Any]]:
    runs = db.list_strategy_runs_all()
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for run in runs:
        key = (run["strategy_key"], run["symbol"], run["ruleset_hash"])
        grouped.setdefault(key, []).append(run)
    summaries = []
    for (strategy_key, symbol, ruleset_hash_value), items in grouped.items():
        n_total = len(items)
        passed = [r for r in items if r["result"] == "PASSED"]
        failed = [r for r in items if r["result"] == "FAILED"]
        pass_rate = (len(passed) / n_total) if n_total else 0.0
        median_days = _median(
            [
                _days_between(r["started_at"], r["ended_at"])
                for r in passed
                if r.get("started_at") and r.get("ended_at")
            ]
        )
        median_trades = _median([r["trades_count"] for r in passed])
        avg_max_dd = _average([r["max_dd_used_pct"] for r in items])
        avg_daily_dd = _average([r["worst_daily_dd_used_pct"] for r in items])
        avg_pf = _average([r["profit_factor"] for r in items])
        avg_win_rate = _average([r["win_rate"] for r in items])
        avg_net_pnl = _average([r["net_pnl"] for r in items])
        last_run = max((r["ended_at"] for r in items if r.get("ended_at")), default=None)
        action = "run more samples" if n_total < 10 else "review" if pass_rate < 0.5 else "scale"
        family, version = derive_strategy_family(strategy_key)
        summaries.append(
            {
                "strategy_key": strategy_key,
                "strategy_family": family,
                "strategy_version": version,
                "symbol": symbol,
                "ruleset_hash": ruleset_hash_value,
                "n_total": n_total,
                "n_passed": len(passed),
                "n_failed": len(failed),
                "pass_rate": pass_rate,
                "median_days_to_pass": median_days,
                "median_trades_to_pass": median_trades,
                "avg_max_dd_used_pct": avg_max_dd,
                "avg_worst_daily_dd_used_pct": avg_daily_dd,
                "avg_profit_factor": avg_pf,
                "avg_win_rate": avg_win_rate,
                "avg_net_pnl": avg_net_pnl,
                "last_run_ended_at": last_run,
                "recommended_next_action": action,
            }
        )
    return summaries


@app.get("/api/strategies/{strategy_key}/runs")
async def strategy_runs(
    strategy_key: str,
    symbol: Optional[str] = None,
    ruleset_hash_value: Optional[str] = Query(None, alias="ruleset_hash"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    return db.list_strategy_runs(strategy_key, symbol, ruleset_hash_value, limit, offset)


@app.get("/api/alerts")
async def alerts() -> dict[str, Any]:
    evals = db.list_evals()
    near_daily = []
    near_max = []
    losing_streaks = []
    for row in evals:
        if row.status not in {"ACTIVE", "PAUSED"}:
            continue
        daily_floor = row.day_start_equity * (1 - row.daily_dd_pct)
        daily_remaining = max(0.0, row.current_equity - daily_floor)
        daily_allowed = row.day_start_equity * row.daily_dd_pct
        daily_remaining_pct = (daily_remaining / daily_allowed) if daily_allowed else 1.0
        if daily_remaining_pct <= 0.2:
            near_daily.append(
                {
                    "eval_id": row.id,
                    "strategy_key": row.strategy_key,
                    "symbol": row.symbol,
                    "remaining_pct": daily_remaining_pct,
                }
            )
        max_floor = row.starting_balance * (1 - row.max_dd_pct)
        max_remaining = max(0.0, row.current_equity - max_floor)
        max_allowed = row.starting_balance * row.max_dd_pct
        max_remaining_pct = (max_remaining / max_allowed) if max_allowed else 1.0
        if max_remaining_pct <= 0.2:
            near_max.append(
                {
                    "eval_id": row.id,
                    "strategy_key": row.strategy_key,
                    "symbol": row.symbol,
                    "remaining_pct": max_remaining_pct,
                }
            )
        closed_positions = db.list_closed_positions_for_eval_limit(row.id, 20)
        streak = _current_streak(closed_positions)
        if streak <= -5:
            losing_streaks.append(
                {
                    "eval_id": row.id,
                    "strategy_key": row.strategy_key,
                    "symbol": row.symbol,
                    "streak": streak,
                }
            )
    feed, ages = price_service.get_health()
    stale_prices = [
        {"symbol": symbol, "age_ms": age}
        for symbol, age in ages.items()
        if age > 15000
    ]
    return {
        "near_daily_dd": near_daily,
        "near_max_dd": near_max,
        "stale_prices": stale_prices,
        "long_losing_streak": losing_streaks,
        "price_feed": feed,
    }


@app.get("/api/activity")
async def activity(limit: int = Query(200, ge=1, le=500)) -> list[dict[str, Any]]:
    rows = db.list_events_global(limit)
    events = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        message = row["type"]
        if isinstance(payload, dict) and payload.get("reason"):
            message = f"{row['type']}: {payload['reason']}"
        events.append(
            {
                "ts": row["ts"],
                "eval_id": row["eval_id"],
                "strategy_key": row["strategy_key"],
                "symbol": row["symbol"],
                "type": row["type"],
                "short_message": message,
            }
        )
    return events


@app.get("/api/system")
async def system_status() -> dict[str, Any]:
    feed, ages = price_service.get_health()
    open_positions = db.list_open_positions()
    total_unrealized = 0.0
    for position in open_positions:
        bar = price_service.get_latest_bar(position.symbol)
        if not bar:
            continue
        entry_fill = position.entry_fill_price or position.entry_price
        if position.side == "LONG":
            total_unrealized += (bar.close - entry_fill) * position.qty
        else:
            total_unrealized += (entry_fill - bar.close) * position.qty
    return {
        "price_feed_source": feed,
        "last_price_update_age_ms": ages,
        "feed_state": eval_manager._feed_state,
        "websocket_clients_connected": ws_manager.connection_count(),
        "open_positions_count": len(open_positions),
        "total_unrealized_pnl": total_unrealized,
        "db_path": db.path,
        "db_wal_enabled": True,
        "last_wal_checkpoint_at": last_wal_checkpoint_at,
        "running_tasks": {"price_service": True, "eval_manager": True},
    }


@app.on_event("startup")
async def startup() -> None:
    logger.info("startup | db.init begin")
    db.init()
    logger.info("startup | db.init done")
    logger.info("startup | price_service.start begin")
    await price_service.start()
    logger.info("startup | price_service.start done")
    logger.info("startup | eval_manager.start begin")
    await eval_manager.start()
    logger.info("startup | eval_manager.start done")
    app.state.wal_task = asyncio.create_task(_wal_checkpoint_loop())
    logger.info("startup | wal checkpoint loop scheduled")


@app.on_event("shutdown")
async def shutdown() -> None:
    await eval_manager.stop()
    await price_service.stop()
    task = getattr(app.state, "wal_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    db.close()


def eval_manager_id() -> str:
    return str(uuid4())


async def _wal_checkpoint_loop() -> None:
    global last_wal_checkpoint_at
    while True:
        await asyncio.sleep(300)
        db.wal_checkpoint()
        last_wal_checkpoint_at = datetime.now(timezone.utc).isoformat()


def _exit_reason(exit_price: Optional[float], stop_price: float, tp_price: Optional[float]) -> str:
    if exit_price is None:
        return "OTHER"
    if exit_price == stop_price:
        return "STOP"
    if tp_price is not None and exit_price == tp_price:
        return "TP"
    return "OTHER"


def _calculate_rr(entry: float, stop: float, tp: Optional[float]) -> Optional[float]:
    if tp is None:
        return None
    risk = abs(entry - stop)
    reward = abs(tp - entry)
    if risk == 0:
        return None
    return reward / risk


def _median(values: list[float]) -> Optional[float]:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return float(statistics.median(cleaned))


def _average(values: list[Optional[float]]) -> Optional[float]:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _days_between(start: str, end: str) -> Optional[float]:
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        return None
    return max(0.0, (end_dt - start_dt).total_seconds() / 86400.0)


def _current_streak(positions: list[Any]) -> int:
    streak = 0
    for position in positions:
        pnl = position.pnl or 0.0
        if pnl > 0:
            if streak < 0:
                break
            streak += 1
        elif pnl < 0:
            if streak > 0:
                break
            streak -= 1
        else:
            break
    return streak


def _insert_strategy_run(
    row: Any,
    closed_positions: list[Any],
    summary: dict[str, Optional[float]],
    result: str,
    fail_reason: Optional[str],
) -> None:
    if db.strategy_run_exists(row.id):
        return
    ruleset = build_ruleset(row)
    family, version = derive_strategy_family(row.strategy_key)
    rules_hash = ruleset_hash(ruleset)
    fees_paid = sum((position.total_fees or 0.0) for position in closed_positions)
    slippage_impact = sum(
        ((position.entry_slippage or 0.0) + (position.exit_slippage or 0.0)) * position.qty
        for position in closed_positions
    )
    win_rate_pct = summary.get("win_rate_pct")
    db.insert_strategy_run(
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
            "ended_at": row.passed_at or datetime.now(timezone.utc).isoformat(),
            "result": result,
            "fail_reason": row.fail_reason or fail_reason,
            "starting_balance": row.starting_balance,
            "ending_equity": row.current_equity,
            "net_pnl": row.current_equity - row.starting_balance,
            "trades_count": len(closed_positions),
            "wins": summary.get("wins") or 0,
            "losses": summary.get("losses") or 0,
            "win_rate": (win_rate_pct / 100) if win_rate_pct is not None else None,
            "profit_factor": summary.get("profit_factor"),
            "max_dd_used_pct": row.max_dd_used_pct,
            "worst_daily_dd_used_pct": row.worst_daily_dd_used_pct,
            "fees_paid": fees_paid,
            "slippage_impact": slippage_impact,
            "notes": None,
        }
    )


def _eval_response(row: Any) -> EvalResponse:
    strategy = db.fetch_strategy(row.strategy_key)
    open_positions = db.list_open_positions_for_eval(row.id)
    last_price = None
    open_pnl = None
    unrealized_equity = None
    open_position_payload = None
    open_position_payloads: list[PositionResponse] = []
    reset_at = None
    reset_remaining = None
    avg_rr = None
    total_fees_paid = None
    total_slippage_impact = None
    summary: dict[str, Optional[float]] = {}
    daily_floor = row.day_start_equity * (1 - row.daily_dd_pct)
    daily_remaining_usd = max(0.0, row.current_equity - daily_floor)
    daily_dd_guard_threshold_usd = max(
        0.0,
        row.risk_usd * (row.daily_dd_guard_risk_multiple or 0.0)
        + row.risk_usd * (row.daily_dd_guard_buffer_pct or 0.0)
        + (row.daily_dd_guard_buffer_usd or 0.0),
    )
    if open_positions:
        total_open_pnl = 0.0
        for position in open_positions:
            open_position_payloads.append(
                PositionResponse(
                    id=position.id,
                    eval_id=position.eval_id,
                    symbol=position.symbol,
                    side=position.side,
                    qty=position.qty,
                    entry_price=position.entry_price,
                    stop_price=position.stop_price,
                    tp_price=position.tp_price,
                    opened_at=position.opened_at,
                    status=position.status,
                    rr=_calculate_rr(position.entry_price, position.stop_price, position.tp_price),
                    entry_fee=position.entry_fee,
                    exit_fee=position.exit_fee,
                    total_fees=position.total_fees,
                    entry_slippage=position.entry_slippage,
                    exit_slippage=position.exit_slippage,
                    entry_fill_price=position.entry_fill_price,
                    exit_fill_price=position.exit_fill_price,
                )
            )
            tick = price_service.get_latest_ticks().get(position.symbol)
            if tick:
                last_price = tick.price
                entry_fill = position.entry_fill_price or position.entry_price
                if position.side == "LONG":
                    total_open_pnl += (tick.price - entry_fill) * position.qty
                else:
                    total_open_pnl += (entry_fill - tick.price) * position.qty
        open_position_payload = open_position_payloads[0]
        open_pnl = total_open_pnl
        unrealized_equity = row.current_balance + total_open_pnl
    try:
        window_start = ensure_aware(datetime.fromisoformat(row.day_window_start_ts))
        reset_at = next_et_midnight(window_start)
        reset_remaining = max(0, int((reset_at - datetime.now(timezone.utc)).total_seconds()))
    except ValueError:
        reset_at = None
        reset_remaining = None
    closed_positions = db.list_closed_positions_for_eval(row.id)
    rolling_positions = db.list_closed_positions_for_eval_limit(row.id, 20)
    summary = summarize_eval(row, closed_positions, rolling_positions)
    if closed_positions:
        total_fees_paid = sum((position.total_fees or 0.0) for position in closed_positions)
        total_slippage_impact = sum(
            ((position.entry_slippage or 0.0) + (position.exit_slippage or 0.0)) * position.qty
            for position in closed_positions
        )
    avg_rr = None
    return EvalResponse(
        id=row.id,
        name=row.name,
        strategy_key=row.strategy_key,
        strategy_name=strategy.name if strategy else None,
        account_type=row.account_type,
        prop_firm_mode=row.prop_firm_mode,
        symbol=row.symbol,
        status=row.status,
        created_at=row.created_at,
        starting_balance=row.starting_balance,
        current_balance=row.current_balance,
        current_equity=row.current_equity,
        day_start_equity=row.day_start_equity,
        day_window_start_ts=row.day_window_start_ts,
        max_dd_pct=row.max_dd_pct,
        daily_dd_pct=row.daily_dd_pct,
        risk_usd=row.risk_usd,
        fees_enabled=bool(row.fees_enabled),
        slippage_enabled=bool(row.slippage_enabled),
        taker_fee_rate=row.taker_fee_rate,
        slippage_min_usd=row.slippage_min_usd,
        slippage_max_usd=row.slippage_max_usd,
        risk_updated_at=row.risk_updated_at or row.created_at,
        latency_enabled=bool(row.latency_enabled),
        latency_min_sec=row.latency_min_sec,
        latency_max_sec=row.latency_max_sec,
        dynamic_tp_enabled=bool(row.dynamic_tp_enabled),
        webhook_passthrough_enabled=bool(strategy.webhook_passthrough_enabled) if strategy else bool(row.webhook_passthrough_enabled),
        webhook_passthrough_url=strategy.webhook_passthrough_url if strategy else row.webhook_passthrough_url,
        profit_target_pct=row.profit_target_pct,
        profit_target_equity=summary.get("profit_target_equity"),
        profit_remaining_usd=summary.get("profit_remaining_usd"),
        profit_progress_pct=summary.get("profit_progress_pct"),
        passed_at=row.passed_at,
        archived_at=row.archived_at,
        fail_reason=row.fail_reason,
        max_dd_used_pct=row.max_dd_used_pct,
        worst_daily_dd_used_pct=row.worst_daily_dd_used_pct,
        last_price=last_price,
        open_pnl=open_pnl,
        unrealized_equity=unrealized_equity,
        has_open_position=bool(open_positions),
        open_position=open_position_payload,
        open_positions=open_position_payloads,
        daily_reset_at_ts=reset_at.isoformat() if reset_at else None,
        daily_reset_seconds_remaining=reset_remaining,
        average_rr=avg_rr,
        avg_win_r=summary.get("avg_win_r"),
        win_rate_r=summary.get("win_rate_r"),
        n_valid_r=summary.get("n_valid_r"),
        n_wins_r=summary.get("n_wins_r"),
        expectancy_r=summary.get("expectancy_r"),
        total_fees_paid=total_fees_paid,
        total_slippage_impact=total_slippage_impact,
        wins=summary.get("wins"),
        losses=summary.get("losses"),
        breakeven=summary.get("breakeven"),
        win_rate_pct=summary.get("win_rate_pct"),
        gross_profit=summary.get("gross_profit"),
        gross_loss=summary.get("gross_loss"),
        profit_factor=summary.get("profit_factor"),
        avg_win=summary.get("avg_win"),
        avg_loss=summary.get("avg_loss"),
        avg_r=None,
        rolling_net_pnl=summary.get("rolling_net_pnl"),
        rolling_avg_pnl_per_trade=summary.get("rolling_avg_pnl_per_trade"),
        rolling_win_rate=summary.get("rolling_win_rate"),
        rolling_profit_factor=summary.get("rolling_profit_factor"),
        rolling_avg_win=summary.get("rolling_avg_win"),
        rolling_avg_loss=summary.get("rolling_avg_loss"),
        expected_trades_to_pass=summary.get("expected_trades_to_pass"),
        expected_days_to_pass=summary.get("expected_days_to_pass"),
        expected_trades_to_daily_fail=summary.get("expected_trades_to_daily_fail"),
        expected_trades_to_max_fail=summary.get("expected_trades_to_max_fail"),
        daily_dd_guard_enabled=bool(row.daily_dd_guard_enabled),
        daily_dd_guard_risk_multiple=row.daily_dd_guard_risk_multiple or 1.0,
        daily_dd_guard_buffer_pct=row.daily_dd_guard_buffer_pct or 0.0,
        daily_dd_guard_buffer_usd=row.daily_dd_guard_buffer_usd or 0.0,
        daily_dd_guard_auto_resume_on_daily_reset=bool(row.daily_dd_guard_auto_resume_on_daily_reset),
        daily_dd_guard_close_open_positions_on_trigger=bool(row.daily_dd_guard_close_open_positions_on_trigger),
        daily_dd_guard_blocking=bool(row.daily_dd_guard_blocking),
        daily_dd_guard_reason=row.daily_dd_guard_reason,
        daily_dd_guard_threshold_usd=daily_dd_guard_threshold_usd,
        daily_dd_remaining_usd=daily_remaining_usd,
        daily_dd_guard_blocks_entries_until=reset_at.isoformat() if (reset_at and row.daily_dd_guard_blocking) else None,
    )


def _normalize_webhook_passthrough_settings(
    enabled: bool,
    url: Optional[str],
) -> tuple[bool, Optional[str], Optional[str]]:
    cleaned = (url or "").strip()
    if not enabled:
        return False, cleaned or None, None
    if not cleaned:
        return False, None, "Webhook passthrough URL is required when passthrough is enabled"
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, None, "Webhook passthrough URL must be a full http(s) URL"
    return True, cleaned, None


def _forward_webhook_passthrough(
    strategy_key: str,
    raw_body: bytes,
    content_type: Optional[str],
) -> None:
    urls = db.list_webhook_passthrough_urls(strategy_key)
    if not urls:
        return
    for url in urls:
        threading.Thread(
            target=_post_webhook_passthrough,
            args=(url, raw_body, content_type),
            daemon=True,
        ).start()


def _post_webhook_passthrough(url: str, raw_body: bytes, content_type: Optional[str]) -> None:
    req = urllib.request.Request(
        url=url,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": content_type or "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=3):
            return
    except urllib.error.URLError as exc:
        logger.warning("passthrough webhook failed | %s | %s", url, exc)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
