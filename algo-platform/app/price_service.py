from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import websockets

from .db import Database, PriceRow
from .market_data_matrix import LIVE_MARKET_DATA_ROWS
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
        self._history: dict[str, list[PriceTick]] = {}
        self._lock = threading.Lock()
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False
        self._timeframe = "tick"
        self._source = "okx"
        self._last_broadcast_ts = 0.0
        self._last_parse_log = 0.0
        self._last_persist: dict[str, float] = {}
        self._okx_symbols = {
            row.external_ticker: row.instrument_id
            for row in LIVE_MARKET_DATA_ROWS
            if row.provider == "okx"
        }
        self._bybit_spot_symbols = {
            row.external_ticker: row.instrument_id
            for row in LIVE_MARKET_DATA_ROWS
            if row.provider == "bybit_spot"
        }
        self._bybit_linear_symbols = {
            row.external_ticker: row.instrument_id
            for row in LIVE_MARKET_DATA_ROWS
            if row.provider == "bybit_linear"
        }
        self._binance_spot_symbols = {
            row.external_ticker: row.instrument_id
            for row in LIVE_MARKET_DATA_ROWS
            if row.provider == "binance_spot"
        }
        self._binance_futures_symbols = {
            row.external_ticker: row.instrument_id
            for row in LIVE_MARKET_DATA_ROWS
            if row.provider == "binance_futures"
        }

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [asyncio.create_task(self._run_feed("okx", self._consume_okx))]
        if self._bybit_spot_symbols:
            self._tasks.append(asyncio.create_task(self._run_feed("bybit_spot", self._consume_bybit_spot)))
        if self._bybit_linear_symbols:
            self._tasks.append(asyncio.create_task(self._run_feed("bybit_linear", self._consume_bybit_linear)))
        if self._binance_spot_symbols:
            self._tasks.append(asyncio.create_task(self._run_feed("binance_spot", self._consume_binance_spot)))
        if self._binance_futures_symbols:
            self._tasks.append(asyncio.create_task(self._run_feed("binance_futures", self._consume_binance_futures)))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []

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

    async def _run_feed(self, feed_name: str, consumer: Callable[[], Awaitable[None]]) -> None:
        backoff = 1.0
        while self._running:
            try:
                await consumer()
                backoff = 1.0
            except Exception as exc:
                self._logger.warning("price feed error (%s): %s", feed_name, exc)
                backoff = min(backoff * 2, 30.0)
                await asyncio.sleep(backoff)
                self._logger.info("reconnecting to %s in %.1fs", feed_name, backoff)

    async def _consume_okx(self) -> None:
        url = "wss://ws.okx.com:8443/ws/v5/public"
        self._logger.info("connecting to okx ws")
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            for chunk in self._batched(sorted(self._okx_symbols), 50):
                await ws.send(
                    json.dumps(
                        {
                            "op": "subscribe",
                            "args": [{"channel": "tickers", "instId": inst_id} for inst_id in chunk],
                        }
                    )
                )
            self._logger.info("okx subscribe sent for %s symbols", len(self._okx_symbols))
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
        mapped = self._okx_symbols.get(inst_id)
        if not mapped:
            return
        try:
            price = float(last)
        except ValueError:
            return
        ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
        self._update_tick(mapped, price, "okx", ts)

    async def _consume_bybit_spot(self) -> None:
        await self._consume_bybit_feed(
            feed_name="bybit spot",
            uri="wss://stream.bybit.com/v5/public/spot",
            symbols=self._bybit_spot_symbols,
            source="bybit_spot",
        )

    async def _consume_bybit_linear(self) -> None:
        await self._consume_bybit_feed(
            feed_name="bybit linear",
            uri="wss://stream.bybit.com/v5/public/linear",
            symbols=self._bybit_linear_symbols,
            source="bybit_linear",
        )

    async def _consume_bybit_feed(
        self,
        feed_name: str,
        uri: str,
        symbols: dict[str, str],
        source: str,
    ) -> None:
        self._logger.info("connecting to %s ws", feed_name)
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
            for chunk in self._batched(sorted(symbols), 10):
                await ws.send(json.dumps({"op": "subscribe", "args": [f"tickers.{symbol}" for symbol in chunk]}))
                await asyncio.sleep(0.25)
            self._logger.info("%s subscribe sent for %s symbols", feed_name, len(symbols))
            while self._running:
                message = await ws.recv()
                self._handle_bybit_message(message, symbols, source)

    def _handle_bybit_message(self, message: str, symbols: dict[str, str], source: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            self._log_parse_failure(f"{source} json decode")
            return
        topic = payload.get("topic")
        if not isinstance(topic, str) or not topic.startswith("tickers."):
            return
        data = payload.get("data")
        if not isinstance(data, dict):
            return
        external_symbol = data.get("symbol")
        last = data.get("lastPrice")
        if not isinstance(external_symbol, str) or last is None:
            return
        mapped = symbols.get(external_symbol)
        if not mapped:
            return
        try:
            price = float(last)
        except ValueError:
            return
        ts_ms = payload.get("ts")
        ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
        self._update_tick(mapped, price, source, ts)

    async def _consume_binance_spot(self) -> None:
        await self._consume_binance_feed(
            feed_name="binance spot",
            uri=self._binance_combined_uri(
                "wss://data-stream.binance.vision/stream", self._binance_spot_symbols
            ),
            symbols=self._binance_spot_symbols,
            source="binance_spot",
        )

    async def _consume_binance_futures(self) -> None:
        await self._consume_binance_feed(
            feed_name="binance futures",
            uri=self._binance_combined_uri(
                "wss://fstream.binance.com/stream", self._binance_futures_symbols
            ),
            symbols=self._binance_futures_symbols,
            source="binance_futures",
        )

    async def _consume_binance_feed(
        self,
        feed_name: str,
        uri: str,
        symbols: dict[str, str],
        source: str,
    ) -> None:
        self._logger.info("connecting to %s ws", feed_name)
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
            self._logger.info("%s subscribe connected for %s symbols", feed_name, len(symbols))
            while self._running:
                message = await ws.recv()
                self._handle_binance_message(message, symbols, source)

    def _handle_binance_message(self, message: str, symbols: dict[str, str], source: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            self._log_parse_failure(f"{source} json decode")
            return
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return
        external_symbol = data.get("s")
        last = data.get("c")
        if not isinstance(external_symbol, str) or last is None:
            return
        mapped = symbols.get(external_symbol.upper())
        if not mapped:
            return
        try:
            price = float(last)
        except ValueError:
            return
        ts_ms = data.get("E")
        ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
        self._update_tick(mapped, price, source, ts)

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

    @staticmethod
    def _batched(items: list[str], size: int) -> list[list[str]]:
        return [items[idx : idx + size] for idx in range(0, len(items), size)]

    @staticmethod
    def _binance_combined_uri(base_uri: str, symbols: dict[str, str]) -> str:
        streams = "/".join(f"{symbol.lower()}@ticker" for symbol in sorted(symbols))
        return f"{base_uri}?streams={streams}"
