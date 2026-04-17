from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from contextlib import contextmanager
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    return utc_now().isoformat()


@dataclass(frozen=True)
class EvalRow:
    id: str
    name: str
    strategy_key: str
    account_type: str
    prop_firm_mode: Optional[str]
    symbol: str
    rules_json: str
    status: str
    created_at: str
    risk_usd: float
    starting_balance: float
    current_balance: float
    current_equity: float
    day_start_equity: float
    day_window_start_ts: str
    last_daily_reset_day: Optional[str]
    max_dd_pct: float
    daily_dd_pct: float
    fees_enabled: int
    slippage_enabled: int
    taker_fee_rate: float
    slippage_min_usd: float
    slippage_max_usd: float
    risk_updated_at: str
    profit_target_pct: Optional[float]
    passed_at: Optional[str]
    archived_at: Optional[str]
    stats_cache_json: Optional[str]
    fail_reason: Optional[str]
    max_dd_used_pct: Optional[float]
    worst_daily_dd_used_pct: Optional[float]
    latency_enabled: int
    latency_min_sec: int
    latency_max_sec: int
    dynamic_tp_enabled: int
    webhook_passthrough_enabled: int
    webhook_passthrough_url: Optional[str]
    daily_dd_guard_enabled: int
    daily_dd_guard_risk_multiple: float
    daily_dd_guard_buffer_pct: float
    daily_dd_guard_buffer_usd: float
    daily_dd_guard_auto_resume_on_daily_reset: int
    daily_dd_guard_close_open_positions_on_trigger: int
    daily_dd_guard_blocking: int
    daily_dd_guard_blocked_at: Optional[str]
    daily_dd_guard_reason: Optional[str]


@dataclass(frozen=True)
class StrategyRow:
    key: str
    name: str
    symbol: str
    created_at: str
    updated_at: str
    webhook_passthrough_enabled: int
    webhook_passthrough_url: Optional[str]


@dataclass(frozen=True)
class PositionRow:
    id: str
    eval_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_price: float
    tp_price: Optional[float]
    tp_disabled: int
    tp_source: Optional[str]
    opened_at: str
    closed_at: Optional[str]
    status: str
    exit_price: Optional[float]
    r_multiple: Optional[float]
    pnl: Optional[float]
    fees: Optional[float]
    entry_fee: Optional[float]
    exit_fee: Optional[float]
    total_fees: Optional[float]
    entry_slippage: Optional[float]
    exit_slippage: Optional[float]
    entry_fill_price: Optional[float]
    exit_fill_price: Optional[float]
    risk_usd: Optional[float]
    reason: Optional[str]
    last_checked_ts: Optional[str]
    last_checked_price: Optional[float]


@dataclass(frozen=True)
class PendingFillRow:
    id: str
    eval_id: str
    position_id: Optional[str]
    action: str
    side: str
    qty: float
    intended_price: float
    stop_price: Optional[float]
    tp_price: Optional[float]
    scheduled_ts: str
    created_ts: str
    status: str


@dataclass(frozen=True)
class EquityPointRow:
    eval_id: str
    ts: str
    equity: float
    drawdown_pct: float
    daily_dd_limit_equity: float
    max_dd_limit_equity: float


@dataclass(frozen=True)
class EventRow:
    id: str
    eval_id: str
    ts: str
    type: str
    payload_json: str


@dataclass(frozen=True)
class PriceRow:
    ts: str
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    source: str


class Database:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.path = path

    def init(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA busy_timeout=3000;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategies (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    symbol TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    webhook_passthrough_enabled INTEGER NOT NULL DEFAULT 0,
                    webhook_passthrough_url TEXT
                )
                """
            )
            for statement in (
                "ALTER TABLE strategies ADD COLUMN symbol TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE strategies ADD COLUMN webhook_passthrough_enabled INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE strategies ADD COLUMN webhook_passthrough_url TEXT",
                "ALTER TABLE strategies ADD COLUMN created_at TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE strategies ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
            ):
                try:
                    self._conn.execute(statement)
                except sqlite3.OperationalError:
                    pass
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evals (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    strategy_key TEXT NOT NULL,
                    account_type TEXT NOT NULL DEFAULT 'REGULAR',
                    prop_firm_mode TEXT,
                    symbol TEXT NOT NULL,
                    rules_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    risk_usd REAL NOT NULL DEFAULT 50.0,
                    starting_balance REAL NOT NULL,
                    current_balance REAL NOT NULL,
                    current_equity REAL NOT NULL,
                    day_start_equity REAL NOT NULL,
                    day_window_start_ts TEXT NOT NULL,
                    last_daily_reset_day TEXT,
                    max_dd_pct REAL NOT NULL,
                    daily_dd_pct REAL NOT NULL,
                    fees_enabled INTEGER NOT NULL DEFAULT 1,
                    slippage_enabled INTEGER NOT NULL DEFAULT 1,
                    taker_fee_rate REAL NOT NULL DEFAULT 0.0004,
                    slippage_min_usd REAL NOT NULL DEFAULT 2.0,
                    slippage_max_usd REAL NOT NULL DEFAULT 20.0,
                    risk_updated_at TEXT NOT NULL DEFAULT '',
                    profit_target_pct REAL,
                    passed_at TEXT,
                    archived_at TEXT,
                    stats_cache_json TEXT,
                    fail_reason TEXT,
                    max_dd_used_pct REAL,
                    worst_daily_dd_used_pct REAL,
                    latency_enabled INTEGER NOT NULL DEFAULT 1,
                    latency_min_sec INTEGER NOT NULL DEFAULT 2,
                    latency_max_sec INTEGER NOT NULL DEFAULT 10,
                    dynamic_tp_enabled INTEGER NOT NULL DEFAULT 0,
                    webhook_passthrough_enabled INTEGER NOT NULL DEFAULT 0,
                    webhook_passthrough_url TEXT,
                    daily_dd_guard_enabled INTEGER NOT NULL DEFAULT 0,
                    daily_dd_guard_risk_multiple REAL NOT NULL DEFAULT 1.0,
                    daily_dd_guard_buffer_pct REAL NOT NULL DEFAULT 0.1,
                    daily_dd_guard_buffer_usd REAL NOT NULL DEFAULT 0.0,
                    daily_dd_guard_auto_resume_on_daily_reset INTEGER NOT NULL DEFAULT 1,
                    daily_dd_guard_close_open_positions_on_trigger INTEGER NOT NULL DEFAULT 0,
                    daily_dd_guard_blocking INTEGER NOT NULL DEFAULT 0,
                    daily_dd_guard_blocked_at TEXT,
                    daily_dd_guard_reason TEXT
                )
                """
            )
            try:
                self._conn.execute("ALTER TABLE evals ADD COLUMN risk_usd REAL NOT NULL DEFAULT 50.0")
            except sqlite3.OperationalError:
                pass
            for statement in (
                "ALTER TABLE evals ADD COLUMN fees_enabled INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE evals ADD COLUMN account_type TEXT NOT NULL DEFAULT 'REGULAR'",
                "ALTER TABLE evals ADD COLUMN prop_firm_mode TEXT",
                "ALTER TABLE evals ADD COLUMN slippage_enabled INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE evals ADD COLUMN taker_fee_rate REAL NOT NULL DEFAULT 0.0004",
                "ALTER TABLE evals ADD COLUMN slippage_min_usd REAL NOT NULL DEFAULT 2.0",
                "ALTER TABLE evals ADD COLUMN slippage_max_usd REAL NOT NULL DEFAULT 20.0",
                "ALTER TABLE evals ADD COLUMN risk_updated_at TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE evals ADD COLUMN profit_target_pct REAL",
                "ALTER TABLE evals ADD COLUMN passed_at TEXT",
                "ALTER TABLE evals ADD COLUMN archived_at TEXT",
                "ALTER TABLE evals ADD COLUMN stats_cache_json TEXT",
                "ALTER TABLE evals ADD COLUMN fail_reason TEXT",
                "ALTER TABLE evals ADD COLUMN max_dd_used_pct REAL",
                "ALTER TABLE evals ADD COLUMN worst_daily_dd_used_pct REAL",
                "ALTER TABLE evals ADD COLUMN latency_enabled INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE evals ADD COLUMN latency_min_sec INTEGER NOT NULL DEFAULT 2",
                "ALTER TABLE evals ADD COLUMN latency_max_sec INTEGER NOT NULL DEFAULT 10",
                "ALTER TABLE evals ADD COLUMN dynamic_tp_enabled INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evals ADD COLUMN webhook_passthrough_enabled INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evals ADD COLUMN webhook_passthrough_url TEXT",
                "ALTER TABLE evals ADD COLUMN last_daily_reset_day TEXT",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_enabled INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_risk_multiple REAL NOT NULL DEFAULT 1.0",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_buffer_pct REAL NOT NULL DEFAULT 0.1",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_buffer_usd REAL NOT NULL DEFAULT 0.0",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_auto_resume_on_daily_reset INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_close_open_positions_on_trigger INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_blocking INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_blocked_at TEXT",
                "ALTER TABLE evals ADD COLUMN daily_dd_guard_reason TEXT",
            ):
                try:
                    self._conn.execute(statement)
                except sqlite3.OperationalError:
                    pass
            self._migrate_strategies_from_evals()
            self._migrate_eval_daily_reset_day()
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    eval_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    tp_price REAL,
                    tp_disabled INTEGER NOT NULL DEFAULT 0,
                    tp_source TEXT,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    status TEXT NOT NULL,
                    exit_price REAL,
                    r_multiple REAL,
                    pnl REAL,
                    fees REAL,
                    entry_fee REAL,
                    exit_fee REAL,
                    total_fees REAL,
                    entry_slippage REAL,
                    exit_slippage REAL,
                    entry_fill_price REAL,
                    exit_fill_price REAL,
                    risk_usd REAL,
                    reason TEXT,
                    last_checked_ts TEXT,
                    last_checked_price REAL,
                    FOREIGN KEY(eval_id) REFERENCES evals(id)
                )
                """
            )
            for statement in (
                "ALTER TABLE positions ADD COLUMN entry_fee REAL",
                "ALTER TABLE positions ADD COLUMN exit_fee REAL",
                "ALTER TABLE positions ADD COLUMN total_fees REAL",
                "ALTER TABLE positions ADD COLUMN entry_slippage REAL",
                "ALTER TABLE positions ADD COLUMN exit_slippage REAL",
                "ALTER TABLE positions ADD COLUMN entry_fill_price REAL",
                "ALTER TABLE positions ADD COLUMN exit_fill_price REAL",
                "ALTER TABLE positions ADD COLUMN risk_usd REAL",
                "ALTER TABLE positions ADD COLUMN reason TEXT",
                "ALTER TABLE positions ADD COLUMN last_checked_ts TEXT",
                "ALTER TABLE positions ADD COLUMN last_checked_price REAL",
                "ALTER TABLE positions ADD COLUMN tp_disabled INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE positions ADD COLUMN tp_source TEXT",
                "ALTER TABLE positions ADD COLUMN r_multiple REAL",
            ):
                try:
                    self._conn.execute(statement)
                except sqlite3.OperationalError:
                    pass
            self._migrate_positions_tp_nullable()
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    eval_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(eval_id) REFERENCES evals(id)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    eval_id TEXT,
                    strategy_key TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS signals_unique ON signals(strategy_key, symbol, signal_id)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prices (
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (ts, symbol, timeframe)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_fills (
                    id TEXT PRIMARY KEY,
                    eval_id TEXT NOT NULL,
                    position_id TEXT,
                    action TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL NOT NULL,
                    intended_price REAL NOT NULL,
                    stop_price REAL,
                    tp_price REAL,
                    scheduled_ts TEXT NOT NULL,
                    created_ts TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY(eval_id) REFERENCES evals(id)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS equity_series (
                    eval_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    equity REAL NOT NULL,
                    drawdown_pct REAL NOT NULL,
                    daily_dd_limit_equity REAL NOT NULL,
                    max_dd_limit_equity REAL NOT NULL,
                    PRIMARY KEY (eval_id, ts),
                    FOREIGN KEY(eval_id) REFERENCES evals(id)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_runs (
                    id TEXT PRIMARY KEY,
                    eval_id TEXT NOT NULL,
                    strategy_key TEXT NOT NULL,
                    strategy_family TEXT,
                    strategy_version TEXT,
                    symbol TEXT NOT NULL,
                    ruleset_json TEXT NOT NULL,
                    ruleset_hash TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    result TEXT NOT NULL,
                    fail_reason TEXT,
                    starting_balance REAL NOT NULL,
                    ending_equity REAL NOT NULL,
                    net_pnl REAL NOT NULL,
                    trades_count INTEGER NOT NULL,
                    wins INTEGER NOT NULL,
                    losses INTEGER NOT NULL,
                    win_rate REAL,
                    profit_factor REAL,
                    max_dd_used_pct REAL,
                    worst_daily_dd_used_pct REAL,
                    fees_paid REAL,
                    slippage_impact REAL,
                    notes TEXT
                )
                """
            )
            self._conn.commit()

    def _migrate_positions_tp_nullable(self) -> None:
        cur = self._conn.execute("PRAGMA table_info(positions)")
        info = {row["name"]: row for row in cur.fetchall()}
        tp_col = info.get("tp_price")
        if not tp_col or tp_col["notnull"] == 0:
            return
        has_tp_disabled = "tp_disabled" in info
        has_tp_source = "tp_source" in info
        has_r_multiple = "r_multiple" in info
        tp_disabled_select = "tp_disabled" if has_tp_disabled else "0"
        tp_source_select = "tp_source" if has_tp_source else "'WEBHOOK'"
        r_multiple_select = "r_multiple" if has_r_multiple else "NULL"
        self._conn.execute(
            """
            CREATE TABLE positions_new (
                id TEXT PRIMARY KEY,
                eval_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                entry_price REAL NOT NULL,
                stop_price REAL NOT NULL,
                tp_price REAL,
                tp_disabled INTEGER NOT NULL DEFAULT 0,
                tp_source TEXT,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                status TEXT NOT NULL,
                exit_price REAL,
                r_multiple REAL,
                pnl REAL,
                fees REAL,
                entry_fee REAL,
                exit_fee REAL,
                total_fees REAL,
                entry_slippage REAL,
                exit_slippage REAL,
                entry_fill_price REAL,
                exit_fill_price REAL,
                risk_usd REAL,
                reason TEXT,
                last_checked_ts TEXT,
                last_checked_price REAL,
                FOREIGN KEY(eval_id) REFERENCES evals(id)
            )
            """
        )
        self._conn.execute(
            f"""
            INSERT INTO positions_new (
                id, eval_id, symbol, side, qty, entry_price, stop_price, tp_price,
                tp_disabled, tp_source, opened_at, closed_at, status, exit_price, r_multiple, pnl, fees,
                entry_fee, exit_fee, total_fees, entry_slippage, exit_slippage,
                entry_fill_price, exit_fill_price, risk_usd, reason,
                last_checked_ts, last_checked_price
            )
            SELECT
                id, eval_id, symbol, side, qty, entry_price, stop_price, tp_price,
                {tp_disabled_select}, {tp_source_select}, opened_at, closed_at, status, exit_price, {r_multiple_select}, pnl, fees,
                entry_fee, exit_fee, total_fees, entry_slippage, exit_slippage,
                entry_fill_price, exit_fill_price, risk_usd, reason,
                last_checked_ts, last_checked_price
            FROM positions
            """
        )
        self._conn.execute("DROP TABLE positions")
        self._conn.execute("ALTER TABLE positions_new RENAME TO positions")

    def _migrate_eval_daily_reset_day(self) -> None:
        cur = self._conn.execute("SELECT id, day_window_start_ts, last_daily_reset_day FROM evals")
        rows = cur.fetchall()
        if not rows:
            return
        tz = ZoneInfo("America/New_York")
        updates = []
        for row in rows:
            if row["last_daily_reset_day"]:
                continue
            day_key = None
            value = row["day_window_start_ts"]
            if value:
                try:
                    ts = datetime.fromisoformat(value)
                except ValueError:
                    ts = None
                if ts:
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    day_key = ts.astimezone(tz).date().isoformat()
            if day_key is None:
                day_key = datetime.now(timezone.utc).astimezone(tz).date().isoformat()
            updates.append((day_key, row["id"]))
        if updates:
            self._conn.executemany(
                "UPDATE evals SET last_daily_reset_day = ? WHERE id = ? AND last_daily_reset_day IS NULL",
                updates,
            )

    @contextmanager
    def transaction(self):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _migrate_strategies_from_evals(self) -> None:
        cur = self._conn.execute(
            """
            SELECT strategy_key,
                   COALESCE(
                       (
                           SELECT e2.symbol
                           FROM evals e2
                           WHERE e2.strategy_key = evals.strategy_key
                           ORDER BY e2.created_at DESC
                           LIMIT 1
                       ),
                       ''
                   ) AS symbol,
                   MIN(created_at) AS created_at,
                   MAX(created_at) AS updated_at,
                   MAX(COALESCE(webhook_passthrough_enabled, 0)) AS webhook_passthrough_enabled,
                   MAX(NULLIF(TRIM(COALESCE(webhook_passthrough_url, '')), '')) AS webhook_passthrough_url
            FROM evals
            WHERE TRIM(COALESCE(strategy_key, '')) <> ''
            GROUP BY strategy_key
            """
        )
        rows = cur.fetchall()
        if not rows:
            return
        fallback_now = utc_iso()
        for row in rows:
            strategy_key = row["strategy_key"]
            created_at = row["created_at"] or fallback_now
            updated_at = row["updated_at"] or created_at
            self._conn.execute(
                """
                INSERT INTO strategies (
                    key, name, created_at, updated_at, webhook_passthrough_enabled, webhook_passthrough_url
                    , symbol
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    name = COALESCE(NULLIF(strategies.name, ''), excluded.name),
                    symbol = CASE
                        WHEN strategies.symbol = '' THEN excluded.symbol
                        ELSE strategies.symbol
                    END,
                    updated_at = CASE
                        WHEN strategies.updated_at = '' THEN excluded.updated_at
                        ELSE strategies.updated_at
                    END,
                    created_at = CASE
                        WHEN strategies.created_at = '' THEN excluded.created_at
                        ELSE strategies.created_at
                    END
                """,
                (
                    strategy_key,
                    strategy_key,
                    created_at,
                    updated_at,
                    int(bool(row["webhook_passthrough_enabled"])),
                    row["webhook_passthrough_url"],
                    row["symbol"],
                ),
            )

    def insert_strategy(self, row: StrategyRow) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO strategies (
                    key, name, symbol, created_at, updated_at, webhook_passthrough_enabled, webhook_passthrough_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.key,
                    row.name,
                    row.symbol,
                    row.created_at,
                    row.updated_at,
                    row.webhook_passthrough_enabled,
                    row.webhook_passthrough_url,
                ),
            )
            self._conn.commit()

    def fetch_strategy(self, key: str) -> Optional[StrategyRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM strategies WHERE key = ?", (key,))
            row = cur.fetchone()
            return StrategyRow(**row) if row else None

    def list_strategies(self) -> list[StrategyRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM strategies ORDER BY updated_at DESC, key ASC")
            return [StrategyRow(**row) for row in cur.fetchall()]

    def update_strategy(
        self,
        key: str,
        name: str,
        symbol: str,
        webhook_passthrough_enabled: int,
        webhook_passthrough_url: Optional[str],
        updated_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE strategies
                SET name = ?,
                    symbol = ?,
                    webhook_passthrough_enabled = ?,
                    webhook_passthrough_url = ?,
                    updated_at = ?
                WHERE key = ?
                """,
                (name, symbol, webhook_passthrough_enabled, webhook_passthrough_url, updated_at, key),
            )
            self._conn.commit()

    def insert_eval(self, row: EvalRow) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO evals (
                    id, name, strategy_key, account_type, prop_firm_mode, symbol, rules_json, status, created_at, risk_usd,
                    starting_balance, current_balance, current_equity,
                    day_start_equity, day_window_start_ts, last_daily_reset_day, max_dd_pct, daily_dd_pct,
                    fees_enabled, slippage_enabled, taker_fee_rate, slippage_min_usd, slippage_max_usd, risk_updated_at,
                    profit_target_pct, passed_at, archived_at, stats_cache_json,
                    fail_reason, max_dd_used_pct, worst_daily_dd_used_pct,
                    latency_enabled, latency_min_sec, latency_max_sec, dynamic_tp_enabled,
                    webhook_passthrough_enabled, webhook_passthrough_url
                    , daily_dd_guard_enabled, daily_dd_guard_risk_multiple, daily_dd_guard_buffer_pct,
                    daily_dd_guard_buffer_usd, daily_dd_guard_auto_resume_on_daily_reset,
                    daily_dd_guard_close_open_positions_on_trigger, daily_dd_guard_blocking,
                    daily_dd_guard_blocked_at, daily_dd_guard_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.id,
                    row.name,
                    row.strategy_key,
                    row.account_type,
                    row.prop_firm_mode,
                    row.symbol,
                    row.rules_json,
                    row.status,
                    row.created_at,
                    row.risk_usd,
                    row.starting_balance,
                    row.current_balance,
                    row.current_equity,
                    row.day_start_equity,
                    row.day_window_start_ts,
                    row.last_daily_reset_day,
                    row.max_dd_pct,
                    row.daily_dd_pct,
                    row.fees_enabled,
                    row.slippage_enabled,
                    row.taker_fee_rate,
                    row.slippage_min_usd,
                    row.slippage_max_usd,
                    row.risk_updated_at,
                    row.profit_target_pct,
                    row.passed_at,
                    row.archived_at,
                    row.stats_cache_json,
                    row.fail_reason,
                    row.max_dd_used_pct,
                    row.worst_daily_dd_used_pct,
                    row.latency_enabled,
                    row.latency_min_sec,
                    row.latency_max_sec,
                    row.dynamic_tp_enabled,
                    row.webhook_passthrough_enabled,
                    row.webhook_passthrough_url,
                    row.daily_dd_guard_enabled,
                    row.daily_dd_guard_risk_multiple,
                    row.daily_dd_guard_buffer_pct,
                    row.daily_dd_guard_buffer_usd,
                    row.daily_dd_guard_auto_resume_on_daily_reset,
                    row.daily_dd_guard_close_open_positions_on_trigger,
                    row.daily_dd_guard_blocking,
                    row.daily_dd_guard_blocked_at,
                    row.daily_dd_guard_reason,
                ),
            )
            self._conn.commit()

    def fetch_eval(self, eval_id: str) -> Optional[EvalRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM evals WHERE id = ?", (eval_id,))
            row = cur.fetchone()
            return EvalRow(**row) if row else None

    def list_evals(self) -> list[EvalRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM evals ORDER BY created_at DESC")
            return [EvalRow(**row) for row in cur.fetchall()]

    def list_evals_filtered(self, status: Optional[str], view: Optional[str]) -> list[EvalRow]:
        query = "SELECT * FROM evals"
        params: list[Any] = []
        clauses = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if view == "active":
            clauses.append("status IN ('ACTIVE', 'PAUSED')")
        if view == "history":
            clauses.append("status IN ('PASSED', 'FAILED') OR archived_at IS NOT NULL")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self._lock:
            cur = self._conn.execute(query, params)
            return [EvalRow(**row) for row in cur.fetchall()]

    def list_active_evals(self) -> list[EvalRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM evals WHERE status = 'ACTIVE'")
            return [EvalRow(**row) for row in cur.fetchall()]

    def list_monitored_evals(self) -> list[EvalRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM evals WHERE status IN ('ACTIVE', 'PAUSED')")
            return [EvalRow(**row) for row in cur.fetchall()]

    def list_webhook_passthrough_urls(self, strategy_key: str) -> list[str]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT webhook_passthrough_url
                FROM strategies
                WHERE key = ?
                  AND webhook_passthrough_enabled = 1
                  AND webhook_passthrough_url IS NOT NULL
                  AND TRIM(webhook_passthrough_url) <> ''
                """,
                (strategy_key,),
            )
            return [row["webhook_passthrough_url"] for row in cur.fetchall()]

    def update_eval_status(self, eval_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE evals SET status = ? WHERE id = ?", (status, eval_id))
            self._conn.commit()

    def update_eval_failure(self, eval_id: str, status: str, fail_reason: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE evals SET status = ?, fail_reason = ? WHERE id = ?",
                (status, fail_reason, eval_id),
            )
            self._conn.commit()

    def delete_eval(self, eval_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM events WHERE eval_id = ?", (eval_id,))
            self._conn.execute("DELETE FROM positions WHERE eval_id = ?", (eval_id,))
            self._conn.execute("DELETE FROM pending_fills WHERE eval_id = ?", (eval_id,))
            self._conn.execute("DELETE FROM equity_series WHERE eval_id = ?", (eval_id,))
            self._conn.execute("DELETE FROM evals WHERE id = ?", (eval_id,))
            self._conn.commit()

    def update_eval_financials(
        self,
        eval_id: str,
        current_balance: float,
        current_equity: float,
        day_start_equity: float,
        day_window_start_ts: str,
        status: Optional[str] = None,
        passed_at: Optional[str] = None,
    ) -> None:
        with self._lock:
            if status:
                self._conn.execute(
                    """
                    UPDATE evals
                    SET current_balance = ?, current_equity = ?, day_start_equity = ?,
                        day_window_start_ts = ?, status = ?, passed_at = COALESCE(?, passed_at)
                    WHERE id = ?
                    """,
                    (
                        current_balance,
                        current_equity,
                        day_start_equity,
                        day_window_start_ts,
                        status,
                        passed_at,
                        eval_id,
                    ),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE evals
                    SET current_balance = ?, current_equity = ?, day_start_equity = ?,
                        day_window_start_ts = ?
                    WHERE id = ?
                    """,
                    (
                        current_balance,
                        current_equity,
                        day_start_equity,
                        day_window_start_ts,
                        eval_id,
                    ),
                )
            self._conn.commit()

    def update_eval_dd_stats(
        self, eval_id: str, max_dd_used_pct: float, worst_daily_dd_used_pct: float
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE evals
                SET max_dd_used_pct = ?, worst_daily_dd_used_pct = ?
                WHERE id = ?
                """,
                (max_dd_used_pct, worst_daily_dd_used_pct, eval_id),
            )
            self._conn.commit()

    def apply_daily_reset_if_needed(
        self,
        eval_id: str,
        day_key: str,
        day_start_equity: float,
        day_window_start_ts: str,
    ) -> bool:
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE evals
                SET day_start_equity = ?, day_window_start_ts = ?, last_daily_reset_day = ?
                WHERE id = ? AND (last_daily_reset_day IS NULL OR last_daily_reset_day != ?)
                """,
                (day_start_equity, day_window_start_ts, day_key, eval_id, day_key),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def insert_position(self, row: PositionRow) -> None:
        with self._lock:
            self._conn.execute(
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
                    row.id,
                    row.eval_id,
                    row.symbol,
                    row.side,
                    row.qty,
                    row.entry_price,
                    row.stop_price,
                    row.tp_price,
                    row.tp_disabled,
                    row.tp_source,
                    row.opened_at,
                    row.closed_at,
                    row.status,
                    row.exit_price,
                    row.r_multiple,
                    row.pnl,
                    row.fees,
                    row.entry_fee,
                    row.exit_fee,
                    row.total_fees,
                    row.entry_slippage,
                    row.exit_slippage,
                    row.entry_fill_price,
                    row.exit_fill_price,
                    row.risk_usd,
                    row.reason,
                    row.last_checked_ts,
                    row.last_checked_price,
                ),
            )
            self._conn.commit()

    def close_position(
        self,
        position_id: str,
        closed_at: str,
        exit_price: float,
        r_multiple: Optional[float],
        pnl: float,
        fees: float,
        exit_fee: float,
        total_fees: float,
        exit_slippage: float,
        exit_fill_price: float,
        reason: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE positions
                SET status = 'CLOSED', closed_at = ?, exit_price = ?, r_multiple = ?, pnl = ?, fees = ?,
                    exit_fee = ?, total_fees = ?, exit_slippage = ?, exit_fill_price = ?, reason = ?
                WHERE id = ?
                """,
                (
                    closed_at,
                    exit_price,
                    r_multiple,
                    pnl,
                    fees,
                    exit_fee,
                    total_fees,
                    exit_slippage,
                    exit_fill_price,
                    reason,
                    position_id,
                ),
            )
            self._conn.commit()

    def update_position_check(self, position_id: str, ts: str, price: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE positions SET last_checked_ts = ?, last_checked_price = ? WHERE id = ?",
                (ts, price, position_id),
            )
            self._conn.commit()

    def update_eval_risk(self, eval_id: str, risk_usd: float, updated_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE evals SET risk_usd = ?, risk_updated_at = ? WHERE id = ?",
                (risk_usd, updated_at, eval_id),
            )
            self._conn.commit()

    def update_eval_costs(
        self,
        eval_id: str,
        fees_enabled: int,
        slippage_enabled: int,
        taker_fee_rate: float,
        slippage_min_usd: float,
        slippage_max_usd: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE evals
                SET fees_enabled = ?, slippage_enabled = ?, taker_fee_rate = ?,
                    slippage_min_usd = ?, slippage_max_usd = ?
                WHERE id = ?
                """,
                (
                    fees_enabled,
                    slippage_enabled,
                    taker_fee_rate,
                    slippage_min_usd,
                    slippage_max_usd,
                    eval_id,
                ),
            )
            self._conn.commit()

    def update_eval_latency(
        self, eval_id: str, latency_enabled: int, latency_min_sec: int, latency_max_sec: int
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE evals
                SET latency_enabled = ?, latency_min_sec = ?, latency_max_sec = ?
                WHERE id = ?
                """,
                (latency_enabled, latency_min_sec, latency_max_sec, eval_id),
            )
            self._conn.commit()

    def update_eval_profit_target(self, eval_id: str, profit_target_pct: Optional[float]) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE evals SET profit_target_pct = ? WHERE id = ?",
                (profit_target_pct, eval_id),
            )
            self._conn.commit()

    def update_eval_dynamic_tp(self, eval_id: str, dynamic_tp_enabled: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE evals SET dynamic_tp_enabled = ? WHERE id = ?",
                (dynamic_tp_enabled, eval_id),
            )
            self._conn.commit()

    def update_eval_webhook_passthrough(
        self,
        eval_id: str,
        enabled: int,
        url: Optional[str],
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE evals SET webhook_passthrough_enabled = ?, webhook_passthrough_url = ? WHERE id = ?",
                (enabled, url, eval_id),
            )
            self._conn.commit()

    def update_eval_daily_dd_guard(
        self,
        eval_id: str,
        enabled: int,
        risk_multiple: float,
        buffer_pct: float,
        buffer_usd: float,
        auto_resume_on_daily_reset: int,
        close_open_positions_on_trigger: int,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE evals
                SET daily_dd_guard_enabled = ?,
                    daily_dd_guard_risk_multiple = ?,
                    daily_dd_guard_buffer_pct = ?,
                    daily_dd_guard_buffer_usd = ?,
                    daily_dd_guard_auto_resume_on_daily_reset = ?,
                    daily_dd_guard_close_open_positions_on_trigger = ?
                WHERE id = ?
                """,
                (
                    enabled,
                    risk_multiple,
                    buffer_pct,
                    buffer_usd,
                    auto_resume_on_daily_reset,
                    close_open_positions_on_trigger,
                    eval_id,
                ),
            )
            self._conn.commit()

    def update_eval_daily_dd_guard_state(
        self,
        eval_id: str,
        blocking: int,
        blocked_at: Optional[str],
        reason: Optional[str],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE evals
                SET daily_dd_guard_blocking = ?,
                    daily_dd_guard_blocked_at = ?,
                    daily_dd_guard_reason = ?
                WHERE id = ?
                """,
                (blocking, blocked_at, reason, eval_id),
            )
            self._conn.commit()

    def insert_pending_fill(self, row: PendingFillRow) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO pending_fills (
                    id, eval_id, position_id, action, side, qty, intended_price,
                    stop_price, tp_price, scheduled_ts, created_ts, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.id,
                    row.eval_id,
                    row.position_id,
                    row.action,
                    row.side,
                    row.qty,
                    row.intended_price,
                    row.stop_price,
                    row.tp_price,
                    row.scheduled_ts,
                    row.created_ts,
                    row.status,
                ),
            )
            self._conn.commit()

    def list_pending_fills_due(self, now_ts: str) -> list[PendingFillRow]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM pending_fills WHERE status = 'PENDING' AND scheduled_ts <= ? ORDER BY scheduled_ts ASC",
                (now_ts,),
            )
            return [PendingFillRow(**row) for row in cur.fetchall()]

    def has_pending_fill_for_position(self, position_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM pending_fills WHERE position_id = ? AND status = 'PENDING' LIMIT 1",
                (position_id,),
            )
            return cur.fetchone() is not None

    def update_pending_fill_status(self, fill_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE pending_fills SET status = ? WHERE id = ?",
                (status, fill_id),
            )
            self._conn.commit()

    def cancel_pending_fills(self, eval_id: str) -> list[PendingFillRow]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM pending_fills WHERE eval_id = ? AND status = 'PENDING'",
                (eval_id,),
            )
            rows = [PendingFillRow(**row) for row in cur.fetchall()]
            if rows:
                self._conn.execute(
                    "UPDATE pending_fills SET status = 'CANCELLED' WHERE eval_id = ? AND status = 'PENDING'",
                    (eval_id,),
                )
                self._conn.commit()
            return rows

    def insert_equity_point(self, row: EquityPointRow) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO equity_series (
                    eval_id, ts, equity, drawdown_pct, daily_dd_limit_equity, max_dd_limit_equity
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row.eval_id,
                    row.ts,
                    row.equity,
                    row.drawdown_pct,
                    row.daily_dd_limit_equity,
                    row.max_dd_limit_equity,
                ),
            )
            self._conn.commit()

    def list_equity_series(self, eval_id: str, limit: int = 500) -> list[EquityPointRow]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM equity_series
                WHERE eval_id = ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (eval_id, limit),
            )
            return [EquityPointRow(**row) for row in cur.fetchall()]

    def archive_eval(self, eval_id: str, archived_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE evals SET archived_at = ? WHERE id = ?",
                (archived_at, eval_id),
            )
            self._conn.commit()

    def list_closed_positions_for_eval_limit(self, eval_id: str, limit: int) -> list[PositionRow]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM positions WHERE status = 'CLOSED' AND eval_id = ? ORDER BY closed_at DESC LIMIT ?",
                (eval_id, limit),
            )
            return [PositionRow(**row) for row in cur.fetchall()]

    def strategy_run_exists(self, eval_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM strategy_runs WHERE eval_id = ? LIMIT 1",
                (eval_id,),
            )
            return cur.fetchone() is not None

    def insert_strategy_run(self, row: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO strategy_runs (
                    id, eval_id, strategy_key, strategy_family, strategy_version, symbol,
                    ruleset_json, ruleset_hash, started_at, ended_at, result, fail_reason,
                    starting_balance, ending_equity, net_pnl, trades_count, wins, losses,
                    win_rate, profit_factor, max_dd_used_pct, worst_daily_dd_used_pct,
                    fees_paid, slippage_impact, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["eval_id"],
                    row["strategy_key"],
                    row["strategy_family"],
                    row["strategy_version"],
                    row["symbol"],
                    row["ruleset_json"],
                    row["ruleset_hash"],
                    row["started_at"],
                    row["ended_at"],
                    row["result"],
                    row.get("fail_reason"),
                    row["starting_balance"],
                    row["ending_equity"],
                    row["net_pnl"],
                    row["trades_count"],
                    row["wins"],
                    row["losses"],
                    row.get("win_rate"),
                    row.get("profit_factor"),
                    row.get("max_dd_used_pct"),
                    row.get("worst_daily_dd_used_pct"),
                    row.get("fees_paid"),
                    row.get("slippage_impact"),
                    row.get("notes"),
                ),
            )
            self._conn.commit()

    def list_strategy_runs(
        self,
        strategy_key: str,
        symbol: Optional[str],
        ruleset_hash: Optional[str],
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM strategy_runs WHERE strategy_key = ?"
        params: list[Any] = [strategy_key]
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if ruleset_hash:
            query += " AND ruleset_hash = ?"
            params.append(ruleset_hash)
        query += " ORDER BY ended_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock:
            cur = self._conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def list_strategy_runs_all(self) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM strategy_runs")
            return [dict(row) for row in cur.fetchall()]

    def list_events_global(self, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT events.ts, events.eval_id, events.type, events.payload_json,
                       evals.strategy_key, evals.symbol
                FROM events
                JOIN evals ON evals.id = events.eval_id
                ORDER BY events.ts DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_open_positions(self) -> list[PositionRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM positions WHERE status = 'OPEN'")
            return [PositionRow(**row) for row in cur.fetchall()]

    def list_open_positions_for_eval(self, eval_id: str) -> list[PositionRow]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM positions WHERE status = 'OPEN' AND eval_id = ?",
                (eval_id,),
            )
            return [PositionRow(**row) for row in cur.fetchall()]

    def fetch_position(self, position_id: str) -> Optional[PositionRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
            row = cur.fetchone()
            return PositionRow(**row) if row else None

    def list_closed_positions_for_eval(self, eval_id: str) -> list[PositionRow]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM positions WHERE status = 'CLOSED' AND eval_id = ? ORDER BY closed_at DESC",
                (eval_id,),
            )
            return [PositionRow(**row) for row in cur.fetchall()]

    def list_closed_positions_missing_r_multiple(self, limit: int = 1000) -> list[PositionRow]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM positions
                WHERE status = 'CLOSED' AND r_multiple IS NULL
                ORDER BY closed_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [PositionRow(**row) for row in cur.fetchall()]

    def update_position_r_multiple(self, position_id: str, r_multiple: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE positions SET r_multiple = ? WHERE id = ?",
                (r_multiple, position_id),
            )
            self._conn.commit()

    def insert_event(self, row: EventRow) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO events (id, eval_id, ts, type, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (row.id, row.eval_id, row.ts, row.type, row.payload_json),
            )
            self._conn.commit()

    def insert_signal(
        self,
        signal_id: str,
        eval_id: Optional[str],
        strategy_key: str,
        symbol: str,
        received_at: str,
        payload_json: str,
    ) -> bool:
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO signals (id, eval_id, strategy_key, symbol, signal_id, received_at, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (signal_id, eval_id, strategy_key, symbol, signal_id, received_at, payload_json),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def wal_checkpoint(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

    def list_events(self, eval_id: str, limit: int) -> list[EventRow]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE eval_id = ? ORDER BY ts DESC LIMIT ?",
                (eval_id, limit),
            )
            return [EventRow(**row) for row in cur.fetchall()]

    def insert_price(self, row: PriceRow) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO prices
                (ts, symbol, timeframe, open, high, low, close, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.ts,
                    row.symbol,
                    row.timeframe,
                    row.open,
                    row.high,
                    row.low,
                    row.close,
                    row.source,
                ),
            )
            self._conn.commit()

    def load_prices(self) -> list[PriceRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM prices")
            return [PriceRow(**row) for row in cur.fetchall()]

    def load_latest_prices_for_symbols(self, symbols: list[str], timeframe: str) -> list[PriceRow]:
        if not symbols:
            return []
        placeholders = ",".join("?" for _ in symbols)
        with self._lock:
            cur = self._conn.execute(
                f"""
                SELECT p.*
                FROM prices p
                JOIN (
                    SELECT symbol, MAX(ts) AS max_ts
                    FROM prices
                    WHERE timeframe = ?
                      AND symbol IN ({placeholders})
                    GROUP BY symbol
                ) latest
                  ON p.symbol = latest.symbol
                 AND p.ts = latest.max_ts
                 AND p.timeframe = ?
                """,
                (timeframe, *symbols, timeframe),
            )
            return [PriceRow(**row) for row in cur.fetchall()]

    def fetch_latest_price(self, symbol: str, timeframe: str) -> Optional[PriceRow]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM prices
                WHERE symbol = ? AND timeframe = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (symbol, timeframe),
            )
            row = cur.fetchone()
            return PriceRow(**row) if row else None

    def load_rules_json(self, eval_id: str) -> Optional[dict[str, Any]]:
        row = self.fetch_eval(eval_id)
        if not row:
            return None
        try:
            return json.loads(row.rules_json)
        except json.JSONDecodeError:
            return None
