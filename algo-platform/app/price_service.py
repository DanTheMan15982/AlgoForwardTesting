from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import websockets

from .db import Database, PriceRow
from .realtime import WebSocketManager, WSMessage


@dataclass(frozen=True)
class PriceBar:
    ts: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    source: str


@dataclass(frozen=True)
class PriceTick:
    ts: datetime
    price: float
    source: str


class PriceService:
    def __init__(self, db: Database, ws: WebSocketManager, poll_interval: float = 10.0) -> None:
        self._db = db
        self._ws = ws
        self._logger = logging.getLogger("price_service")
        self._poll_interval = poll_interval
        self._bars: dict[str, PriceBar] = {}
        self._latest: dict[str, PriceTick] = {}
        self._history: dict[str, list[PriceTick]] = {"BTC": [], "ETH": [], "SOL": []}
        self._lock = threading.Lock()
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._timeframe = "tick"
        self._source = "okx"
        self._last_broadcast_ts = 0.0
        self._last_parse_log = 0.0
        self._last_persist: dict[str, float] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._warm_cache()
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def get_latest_bar(self, symbol: str) -> Optional[PriceBar]:
        with self._lock:
            bar = self._bars.get(symbol)
            if bar:
                return bar
            tick = self._latest.get(symbol)
            if not tick:
                return None
            return PriceBar(
                ts=tick.ts,
                symbol=symbol,
                timeframe=self._timeframe,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                source=tick.source,
            )

    def get_latest_prices(self) -> list[PriceBar]:
        with self._lock:
            return list(self._bars.values())

    def get_latest_ticks(self) -> dict[str, PriceTick]:
        with self._lock:
            return dict(self._latest)

    @property
    def timeframe(self) -> str:
        return self._timeframe

    def get_health(self) -> tuple[str, dict[str, int]]:
        now_ms = int(time.time() * 1000)
        ages: dict[str, int] = {}
        with self._lock:
            for symbol, tick in self._latest.items():
                ages[symbol] = max(0, now_ms - int(tick.ts.timestamp() * 1000))
        return self._source, ages

    def _warm_cache(self) -> None:
        latest: dict[str, PriceRow] = {}
        for row in self._db.load_prices():
            key = row.symbol
            if key not in latest or row.ts > latest[key].ts:
                latest[key] = row
        with self._lock:
            for symbol, row in latest.items():
                ts = datetime.fromisoformat(row.ts)
                tick = PriceTick(ts=ts, price=row.close, source=row.source)
                self._latest[symbol] = tick
                self._bars[symbol] = PriceBar(
                    ts=ts,
                    symbol=symbol,
                    timeframe=row.timeframe,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    source=row.source,
                )

    async def _run(self) -> None:
        backoff = 1.0
        while self._running:
            try:
                await self._consume_okx()
                backoff = 1.0
            except Exception as exc:
                self._logger.warning("price feed error (okx): %s", exc)
                backoff = min(backoff * 2, 30.0)
                await asyncio.sleep(backoff)
                self._logger.info("reconnecting to okx in %.1fs", backoff)

    async def _consume_okx(self) -> None:
        url = "wss://ws.okx.com:8443/ws/v5/public"
        self._logger.info("connecting to okx ws")
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(
                json.dumps(
                    {
                        "op": "subscribe",
                        "args": [
                            {"channel": "tickers", "instId": "BTC-USDT-SWAP"},
                            {"channel": "tickers", "instId": "ETH-USDT-SWAP"},
                            {"channel": "tickers", "instId": "SOL-USDT-SWAP"},
                        ],
                    }
                )
            )
            self._logger.info("okx subscribe sent")
            while self._running:
                message = await ws.recv()
                self._handle_okx_message(message)

    def _handle_okx_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            self._log_parse_failure("okx json decode")
            return

        if payload.get("event") == "subscribe":
            self._logger.info("okx subscribe ok")
            return
        if payload.get("event"):
            return

        if payload.get("arg", {}).get("channel") != "tickers":
            return
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            return
        item = data[0]
        inst_id = item.get("instId")
        last = item.get("last")
        ts_ms = item.get("ts")
        if not inst_id or last is None:
            return
        mapped = {
            "BTC-USDT-SWAP": "BTC",
            "ETH-USDT-SWAP": "ETH",
            "SOL-USDT-SWAP": "SOL",
        }.get(inst_id)
        if not mapped:
            return
        try:
            price = float(last)
        except ValueError:
            return
        ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
        self._update_tick(mapped, price, "okx", ts)

    def _update_tick(self, symbol: str, price: float, source: str, ts: datetime) -> None:
        tick = PriceTick(ts=ts, price=price, source=source)
        with self._lock:
            self._latest[symbol] = tick
            self._bars[symbol] = PriceBar(
                ts=ts,
                symbol=symbol,
                timeframe=self._timeframe,
                open=price,
                high=price,
                low=price,
                close=price,
                source=source,
            )
            history = self._history.setdefault(symbol, [])
            history.append(tick)
            if len(history) > 200:
                history.pop(0)
        self._persist_tick(symbol, tick)
        self._maybe_broadcast()

    def _persist_tick(self, symbol: str, tick: PriceTick) -> None:
        last = self._last_persist.get(symbol, 0.0)
        now = time.monotonic()
        if now - last < 1.0:
            return
        self._last_persist[symbol] = now
        self._db.insert_price(
            PriceRow(
                ts=tick.ts.isoformat(),
                symbol=symbol,
                timeframe=self._timeframe,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                source=tick.source,
            )
        )

    def _maybe_broadcast(self) -> None:
        now = time.monotonic()
        if now - self._last_broadcast_ts < 0.2:
            return
        self._last_broadcast_ts = now
        data = {}
        with self._lock:
            for symbol, tick in self._latest.items():
                data[symbol] = {
                    "ts": tick.ts.isoformat(),
                    "price": tick.price,
                    "source": tick.source,
                }
        asyncio.create_task(self._ws.broadcast(WSMessage(type="prices", data=data)))

    def _log_parse_failure(self, reason: str) -> None:
        now = time.monotonic()
        if now - self._last_parse_log < 60:
            return
        self._last_parse_log = now
        self._logger.warning("price parse issue: %s", reason)
