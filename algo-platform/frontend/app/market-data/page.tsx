"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRealtime } from "@/lib/realtime";
import { formatDateTime, formatPriceValue } from "@/lib/format";
import { exchangeFeedLabel, tradingviewTickerForInstrument } from "@/lib/instruments";
import { useRealtimeStore } from "@/lib/store";

type MatrixRow = {
  instrument_id: string;
  display_name: string;
  asset_class: string;
  market: string;
  exchange: string;
  provider: string;
  provider_type: string;
  external_ticker: string;
  stream_status: string;
  cadence_target: string;
  free_access: boolean;
  current_price?: number | null;
  price_ts?: string | null;
  price_source?: string | null;
  update_age_ms?: number | null;
  notes?: string | null;
};

function formatAge(ageMs?: number | null, ts?: string | null, nowMs?: number) {
  const derivedAge = ts && nowMs ? Math.max(0, nowMs - new Date(ts).getTime()) : null;
  const effectiveAge = ageMs ?? derivedAge;
  if (effectiveAge == null) return "No live tick";
  if (effectiveAge < 1000) return `${effectiveAge} ms`;
  if (effectiveAge < 60000) return `${(effectiveAge / 1000).toFixed(1)} s`;
  return `${(effectiveAge / 60000).toFixed(1)} min`;
}

function statusBadge(streamStatus: string, hasPrice: boolean) {
  if (hasPrice) return <Badge variant="success">Live Now</Badge>;
  if (streamStatus === "live_now") return <Badge variant="warning">Awaiting Tick</Badge>;
  return <Badge variant="default">Listed</Badge>;
}

export default function MarketDataPage() {
  useRealtime();

  const livePrices = useRealtimeStore((s) => s.prices);
  const wsConnected = useRealtimeStore((s) => s.wsConnected);
  const [rows, setRows] = useState<MatrixRow[]>([]);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const res = await fetch("/api/market-data/matrix");
      if (res.ok) {
        setRows(await res.json());
      }
      setLoading(false);
    };
    load();
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const mergedRows = useMemo(() => {
    return rows.map((row) => {
      const live = livePrices[row.instrument_id];
      if (!live) return row;
      return {
        ...row,
        current_price: live.price,
        price_ts: live.ts,
        price_source: live.source,
        update_age_ms: Math.max(0, nowMs - new Date(live.ts).getTime()),
        stream_status: "live_now",
      };
    });
  }, [rows, livePrices, nowMs]);

  const visibleRows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const ranked = [...mergedRows].sort((a, b) => {
      const aLive = a.current_price != null ? 0 : 1;
      const bLive = b.current_price != null ? 0 : 1;
      return aLive - bLive || a.instrument_id.localeCompare(b.instrument_id);
    });
    if (!normalized) return ranked;
    return ranked.filter((row) => {
      const tvTicker = tradingviewTickerForInstrument(row).toLowerCase();
      return (
        row.instrument_id.toLowerCase().includes(normalized) ||
        row.display_name.toLowerCase().includes(normalized) ||
        row.exchange.toLowerCase().includes(normalized) ||
        row.market.toLowerCase().includes(normalized) ||
        tvTicker.includes(normalized)
      );
    });
  }, [mergedRows, query]);

  const liveCount = mergedRows.filter((row) => row.current_price != null).length;
  const freeCount = mergedRows.filter((row) => row.free_access).length;

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.4em] text-neonSoft">Market Data Matrix</p>
          <h2 className="text-2xl font-semibold text-slate-100">Crypto market matrix across spot and perps</h2>
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>The matrix is crypto-only: OKX top 100 USDT spot pairs, plus a cross-venue core covering OKX perps, Bybit spot/perps, and Binance spot/perps.</span>
            <Badge variant={wsConnected ? "success" : "warning"}>
              {wsConnected ? "Realtime Connected" : "Polling Fallback"}
            </Badge>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm uppercase tracking-[0.3em] text-slate-400">Listed Instruments</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold text-slate-100">{mergedRows.length}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm uppercase tracking-[0.3em] text-slate-400">Live Right Now</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold text-success">{liveCount}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm uppercase tracking-[0.3em] text-slate-400">Free Access Candidates</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold text-neon">{freeCount}</CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <CardTitle className="text-xl text-slate-100">Feed Matrix</CardTitle>
              <div className="mt-1 text-sm text-slate-500">
                Search by TradingView-style code, feed, exchange, or internal instrument id.
              </div>
            </div>
            <div className="w-full max-w-sm">
              <Input
                value={query}
                placeholder="Search BTCUSD, BTCUSDT.P, Binance..."
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="mb-3 text-xs text-slate-500 md:hidden">Swipe to view all columns.</div>
          <div className="mb-3 text-xs text-slate-500">
            Showing {visibleRows.length} of {mergedRows.length} rows
          </div>
          {loading ? (
            <div className="rounded-lg border border-border/70 bg-panelSoft/50 px-4 py-8 text-center text-sm text-slate-500">
              Loading market matrix...
            </div>
          ) : null}
          {!loading && visibleRows.length === 0 ? (
            <div className="rounded-lg border border-border/70 bg-panelSoft/50 px-4 py-8 text-center text-sm text-slate-500">
              No instruments match that search.
            </div>
          ) : null}
          {!loading && visibleRows.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Instrument</TableHead>
                  <TableHead>Market</TableHead>
                  <TableHead>Feed</TableHead>
                  <TableHead>Venue Ticker</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead>Age</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Cadence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleRows.map((row) => {
                  const hasPrice = row.current_price != null;
                  return (
                    <TableRow key={row.instrument_id}>
                      <TableCell>
                        <div className="font-mono font-semibold text-slate-100">
                          {tradingviewTickerForInstrument(row)}
                        </div>
                        <div className="text-xs text-slate-500">{row.display_name}</div>
                        <div className="mt-1 text-[11px] text-slate-600">{row.instrument_id}</div>
                      </TableCell>
                      <TableCell>
                        <div className="capitalize text-slate-100">{row.market}</div>
                        <div className="text-xs text-slate-500">{row.asset_class}</div>
                      </TableCell>
                      <TableCell>
                        <div className="text-slate-100">{exchangeFeedLabel(row)}</div>
                        <div className="text-xs text-slate-500">{row.provider}</div>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-slate-300">{row.external_ticker}</TableCell>
                      <TableCell>{statusBadge(row.stream_status, hasPrice)}</TableCell>
                      <TableCell>
                        <div className="font-mono text-slate-100">
                          {hasPrice ? formatPriceValue(row.current_price as number) : "--"}
                        </div>
                        <div className="text-xs text-slate-500">
                          {row.price_ts ? formatDateTime(row.price_ts) : "No price yet"}
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-slate-300">
                        {formatAge(row.update_age_ms, row.price_ts, nowMs)}
                      </TableCell>
                      <TableCell className="text-xs text-slate-300">
                        {row.price_source ?? row.provider_type}
                      </TableCell>
                      <TableCell className="text-xs text-slate-300">{row.cadence_target}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
