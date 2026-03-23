from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class SignalType(str, Enum):
    ENTER = "ENTER"


class Intent(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class RiskModel(str, Enum):
    FIXED_DOLLAR = "FIXED_DOLLAR"


class TradingViewPayload(BaseModel):
    ticker: str
    side: Side
    entry: Optional[float] = None
    stop: float
    tp: Optional[float] = None
    signal_id: Optional[str] = None
    timeframe: Optional[str] = None
    note: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class Instrument(BaseModel):
    symbol: str
    venue: str
    timeframe: str


class Signal(BaseModel):
    type: SignalType
    side: Side
    intent: Intent
    entry: Optional[float] = None
    stop: float
    take_profit: float = Field(..., alias="tp")

    model_config = ConfigDict(populate_by_name=True)


class Risk(BaseModel):
    model: RiskModel
    risk_usd: float


class Tags(BaseModel):
    note: Optional[str] = None


class SignalEvent(BaseModel):
    event_id: UUID
    source: str
    strategy_key: str
    instrument: Instrument
    signal: Signal
    risk: Risk
    tags: Tags


class SuccessResponse(BaseModel):
    event_id: UUID
    strategy_key: str
    accepted: bool = True


class FailureResponse(BaseModel):
    accepted: bool = False
    reason: str


class EvalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    PASSED = "PASSED"


class EventType(str, Enum):
    SIGNAL_RECEIVED = "SIGNAL_RECEIVED"
    ORDER_OPENED = "ORDER_OPENED"
    ORDER_SCHEDULED = "ORDER_SCHEDULED"
    INVALID_TRADE_REJECTED = "INVALID_TRADE_REJECTED"
    DUPLICATE_SIGNAL_IGNORED = "DUPLICATE_SIGNAL_IGNORED"
    PRICE_FEED_STALE = "PRICE_FEED_STALE"
    PRICE_FEED_RESUMED = "PRICE_FEED_RESUMED"
    GAP_RESOLUTION = "GAP_RESOLUTION"
    STOP_HIT = "STOP_HIT"
    TP_HIT = "TP_HIT"
    EVAL_FAILED = "EVAL_FAILED"
    EVAL_PASSED = "EVAL_PASSED"
    PRICE_TICK = "PRICE_TICK"
    HEARTBEAT = "HEARTBEAT"
    ORDER_EXECUTED = "ORDER_EXECUTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    EXIT_ALL_RECEIVED = "EXIT_ALL_RECEIVED"
    POSITION_CLOSED_EXIT_ALL = "POSITION_CLOSED_EXIT_ALL"
    DAILY_DD_GUARD_ACTIVATED = "DAILY_DD_GUARD_ACTIVATED"
    DAILY_DD_GUARD_RELEASED = "DAILY_DD_GUARD_RELEASED"
    DAILY_DD_GUARD_BLOCKED_ENTRY = "DAILY_DD_GUARD_BLOCKED_ENTRY"


class EvalCreateRequest(BaseModel):
    name: str
    strategy_key: str
    symbol: str
    starting_balance: float
    risk_usd: float
    max_dd_pct: float = 0.06
    daily_dd_pct: float = 0.03
    fees_enabled: bool = True
    slippage_enabled: bool = True
    taker_fee_rate: float = 0.0004
    slippage_min_usd: float = 2.0
    slippage_max_usd: float = 20.0
    profit_target_pct: Optional[float] = None
    latency_enabled: bool = True
    latency_min_sec: int = 2
    latency_max_sec: int = 10
    dynamic_tp_enabled: bool = False
    webhook_passthrough_enabled: bool = False
    webhook_passthrough_url: Optional[str] = None


class EvalRiskUpdateRequest(BaseModel):
    risk_usd: float


class EvalCostUpdateRequest(BaseModel):
    fees_enabled: bool
    slippage_enabled: bool
    taker_fee_rate: float
    slippage_min_usd: float
    slippage_max_usd: float


class EvalLatencyUpdateRequest(BaseModel):
    latency_enabled: bool
    latency_min_sec: int
    latency_max_sec: int


class EvalProfitTargetRequest(BaseModel):
    profit_target_pct: Optional[float]


class EvalDynamicTPUpdateRequest(BaseModel):
    dynamic_tp_enabled: bool


class EvalDailyDDGuardUpdateRequest(BaseModel):
    enabled: bool
    risk_multiple: float = 1.0
    buffer_pct: float = 0.1
    buffer_usd: float = 0.0
    auto_resume_on_daily_reset: bool = True
    close_open_positions_on_trigger: bool = False


class EvalWebhookPassthroughUpdateRequest(BaseModel):
    enabled: bool
    url: Optional[str] = None


class EvalResponse(BaseModel):
    id: str
    name: str
    strategy_key: str
    symbol: str
    status: EvalStatus
    created_at: str
    starting_balance: float
    current_balance: float
    current_equity: float
    day_start_equity: float
    day_window_start_ts: str
    max_dd_pct: float
    daily_dd_pct: float
    risk_usd: float
    fees_enabled: bool
    slippage_enabled: bool
    taker_fee_rate: float
    slippage_min_usd: float
    slippage_max_usd: float
    risk_updated_at: str
    latency_enabled: bool
    latency_min_sec: int
    latency_max_sec: int
    dynamic_tp_enabled: bool
    webhook_passthrough_enabled: bool
    webhook_passthrough_url: Optional[str] = None
    profit_target_pct: Optional[float] = None
    profit_target_equity: Optional[float] = None
    profit_remaining_usd: Optional[float] = None
    profit_progress_pct: Optional[float] = None
    passed_at: Optional[str] = None
    archived_at: Optional[str] = None
    fail_reason: Optional[str] = None
    max_dd_used_pct: Optional[float] = None
    worst_daily_dd_used_pct: Optional[float] = None
    last_price: Optional[float] = None
    open_pnl: Optional[float] = None
    unrealized_equity: Optional[float] = None
    has_open_position: bool = False
    open_position: Optional["PositionResponse"] = None
    open_positions: list["PositionResponse"] = []
    daily_reset_at_ts: Optional[str] = None
    daily_reset_seconds_remaining: Optional[int] = None
    average_rr: Optional[float] = None
    avg_win_r: Optional[float] = None
    win_rate_r: Optional[float] = None
    n_valid_r: Optional[int] = None
    n_wins_r: Optional[int] = None
    expectancy_r: Optional[float] = None
    total_fees_paid: Optional[float] = None
    total_slippage_impact: Optional[float] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    breakeven: Optional[int] = None
    win_rate_pct: Optional[float] = None
    gross_profit: Optional[float] = None
    gross_loss: Optional[float] = None
    profit_factor: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    avg_r: Optional[float] = None
    rolling_net_pnl: Optional[float] = None
    rolling_avg_pnl_per_trade: Optional[float] = None
    rolling_win_rate: Optional[float] = None
    rolling_profit_factor: Optional[float] = None
    rolling_avg_win: Optional[float] = None
    rolling_avg_loss: Optional[float] = None
    expected_trades_to_pass: Optional[float] = None
    expected_days_to_pass: Optional[float] = None
    expected_trades_to_daily_fail: Optional[float] = None
    expected_trades_to_max_fail: Optional[float] = None
    daily_dd_guard_enabled: bool = False
    daily_dd_guard_risk_multiple: float = 1.0
    daily_dd_guard_buffer_pct: float = 0.1
    daily_dd_guard_buffer_usd: float = 0.0
    daily_dd_guard_auto_resume_on_daily_reset: bool = True
    daily_dd_guard_close_open_positions_on_trigger: bool = False
    daily_dd_guard_blocking: bool = False
    daily_dd_guard_reason: Optional[str] = None
    daily_dd_guard_threshold_usd: Optional[float] = None
    daily_dd_remaining_usd: Optional[float] = None
    daily_dd_guard_blocks_entries_until: Optional[str] = None


class EvalEventResponse(BaseModel):
    id: str
    eval_id: str
    ts: str
    type: EventType
    payload: dict[str, Any]


class EquityPointResponse(BaseModel):
    ts: str
    equity: float
    drawdown_pct: float
    daily_dd_limit_equity: float
    max_dd_limit_equity: float


class HealthResponse(BaseModel):
    status: str = "ok"
    price_feed: str = "unknown"
    last_price_update_age_ms: dict[str, int] = {}


class PriceTickResponse(BaseModel):
    ts: str
    price: float
    source: str


class TradeResponse(BaseModel):
    id: str
    eval_id: str
    side: str
    qty: float
    entry_price: float
    exit_price: Optional[float]
    pnl: Optional[float]
    opened_at: str
    closed_at: Optional[str]
    status: str
    reason: Optional[str] = None
    r_multiple: Optional[float] = None
    tp_disabled: Optional[bool] = None
    entry_fee: Optional[float] = None
    exit_fee: Optional[float] = None
    total_fees: Optional[float] = None
    entry_slippage: Optional[float] = None
    exit_slippage: Optional[float] = None
    entry_fill_price: Optional[float] = None
    exit_fill_price: Optional[float] = None


class PositionResponse(BaseModel):
    id: str
    eval_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_price: float
    tp_price: Optional[float]
    opened_at: str
    status: str
    rr: Optional[float] = None
    entry_fee: Optional[float] = None
    exit_fee: Optional[float] = None
    total_fees: Optional[float] = None
    entry_slippage: Optional[float] = None
    exit_slippage: Optional[float] = None
    entry_fill_price: Optional[float] = None
    exit_fill_price: Optional[float] = None
