"use client";

import { useEffect, useMemo, useState } from "react";
import { PriceCard } from "@/components/PriceCard";
import { EvalsTable } from "@/components/EvalsTable";
import { NewEvalModal } from "@/components/NewEvalModal";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRealtime } from "@/lib/realtime";
import { useRealtimeStore } from "@/lib/store";
import { formatCurrency } from "@/lib/format";

export default function DashboardPage() {
  const prices = useRealtimeStore((s) => s.prices);
  const setPrices = useRealtimeStore((s) => s.setPrices);
  const setEvals = useRealtimeStore((s) => s.setEvals);
  const evals = useRealtimeStore((s) => Object.values(s.evals));
  const wsConnected = useRealtimeStore((s) => s.wsConnected);
  const [filter, setFilter] = useState<"active" | "passed" | "failed" | "archived">("active");
  const [strategySummary, setStrategySummary] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any>(null);
  const [activity, setActivity] = useState<any[]>([]);
  const [system, setSystem] = useState<any>(null);

  useRealtime();

  useEffect(() => {
    const load = async () => {
      const [pricesRes, evalsRes] = await Promise.all([fetch("/api/prices"), fetch("/api/evals")]);
      if (pricesRes.ok) {
        const data = await pricesRes.json();
        setPrices(data);
      }
      if (evalsRes.ok) {
        const data = await evalsRes.json();
        setEvals(data);
      }
    };
    load();
  }, [setPrices, setEvals]);

  useEffect(() => {
    const load = async () => {
      const [summaryRes, alertsRes, activityRes, systemRes] = await Promise.all([
        fetch("/api/strategies/summary"),
        fetch("/api/alerts"),
        fetch("/api/activity?limit=80"),
        fetch("/api/system")
      ]);
      if (summaryRes.ok) setStrategySummary(await summaryRes.json());
      if (alertsRes.ok) setAlerts(await alertsRes.json());
      if (activityRes.ok) setActivity(await activityRes.json());
      if (systemRes.ok) setSystem(await systemRes.json());
    };
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  const filteredEvals = useMemo(() => {
    if (filter === "active") {
      return evals.filter((row) => row.status === "ACTIVE" || row.status === "PAUSED");
    }
    if (filter === "passed") {
      return evals.filter((row) => row.status === "PASSED");
    }
    if (filter === "failed") {
      return evals.filter((row) => row.status === "FAILED");
    }
    return evals.filter((row) => row.archived_at);
  }, [evals, filter]);

  return (
    <div className="space-y-10">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.4em] text-neonSoft">Market Pulse</p>
          <h2 className="text-2xl font-semibold text-slate-100">Live Prices</h2>
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>Streaming via websocket.</span>
            <Badge variant={wsConnected ? "success" : "warning"}>
              {wsConnected ? "Connected" : "Polling"}
            </Badge>
          </div>
        </div>
        <NewEvalModal />
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {(["BTC", "ETH", "SOL"] as const).map((symbol) => (
          <PriceCard
            key={symbol}
            symbol={symbol}
            price={prices[symbol]?.price}
            ts={prices[symbol]?.ts}
          />
        ))}
      </section>


      <section className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>System Health</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Price feed</span>
              <span>{system?.price_feed_source ?? "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">WS status</span>
              <span>{wsConnected ? "connected" : "polling"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Open positions</span>
              <span>{system?.open_positions_count ?? "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Unrealized P/L</span>
              <span
                className={`tabular ${
                  system?.total_unrealized_pnl == null
                    ? "text-slate-400"
                    : system.total_unrealized_pnl > 0
                      ? "text-success"
                      : system.total_unrealized_pnl < 0
                        ? "text-danger"
                        : "text-slate-400"
                }`}
              >
                {system?.total_unrealized_pnl != null ? formatCurrency(system.total_unrealized_pnl) : "--"}
              </span>
            </div>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Needs Attention</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Near Daily DD</div>
              <div className="flex flex-wrap gap-2">
                {alerts?.near_daily_dd?.length
                  ? alerts.near_daily_dd.map((item: any) => (
                      <Badge key={item.eval_id} variant="warning">
                        {item.strategy_key} {item.symbol}
                      </Badge>
                    ))
                  : <span className="text-slate-500 text-xs">None</span>}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Near Max DD</div>
              <div className="flex flex-wrap gap-2">
                {alerts?.near_max_dd?.length
                  ? alerts.near_max_dd.map((item: any) => (
                      <Badge key={item.eval_id} variant="danger">
                        {item.strategy_key} {item.symbol}
                      </Badge>
                    ))
                  : <span className="text-slate-500 text-xs">None</span>}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Losing streaks</div>
              <div className="flex flex-wrap gap-2">
                {alerts?.long_losing_streak?.length
                  ? alerts.long_losing_streak.map((item: any) => (
                      <Badge key={item.eval_id} variant="warning">
                        {item.strategy_key} {item.symbol} ({item.streak})
                      </Badge>
                    ))
                  : <span className="text-slate-500 text-xs">None</span>}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Stale prices</div>
              <div className="flex flex-wrap gap-2">
                {alerts?.stale_prices?.length
                  ? alerts.stale_prices.map((item: any) => (
                      <Badge key={item.symbol} variant="default">
                        {item.symbol} {Math.round(item.age_ms / 1000)}s
                      </Badge>
                    ))
                  : <span className="text-slate-500 text-xs">None</span>}
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <Card>
          <CardHeader>
            <CardTitle>Strategy Leaderboard</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-auto text-sm">
              <table className="w-full text-left tabular">
                <thead className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  <tr>
                    <th className="pb-2">Strategy</th>
                    <th className="pb-2">Symbol</th>
                    <th className="pb-2 text-right">Pass Rate</th>
                    <th className="pb-2 text-right">Median Days</th>
                    <th className="pb-2 text-right">Median Trades</th>
                    <th className="pb-2 text-right">Avg Max DD</th>
                    <th className="pb-2 text-right">Avg Daily DD</th>
                    <th className="pb-2 text-right">Avg PF</th>
                  </tr>
                </thead>
                <tbody>
                  {strategySummary.map((row) => (
                    <tr key={`${row.strategy_key}-${row.symbol}-${row.ruleset_hash}`} className="border-t border-border/60">
                      <td className="py-2">{row.strategy_key}</td>
                      <td className="py-2">{row.symbol}</td>
                      <td className="py-2 text-right">
                        {Math.round(row.pass_rate * 100)}% (n={row.n_total})
                      </td>
                      <td className="py-2 text-right">{row.median_days_to_pass?.toFixed(1) ?? "--"}</td>
                      <td className="py-2 text-right">{row.median_trades_to_pass?.toFixed(1) ?? "--"}</td>
                      <td className="py-2 text-right">{row.avg_max_dd_used_pct?.toFixed(2) ?? "--"}</td>
                      <td className="py-2 text-right">{row.avg_worst_daily_dd_used_pct?.toFixed(2) ?? "--"}</td>
                      <td className="py-2 text-right">{row.avg_profit_factor?.toFixed(2) ?? "--"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <Card>
          <CardHeader>
            <CardTitle>Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[280px] space-y-2 overflow-y-auto text-sm">
              {activity.map((item) => (
                <div key={`${item.eval_id}-${item.ts}`} className="rounded border border-border/70 bg-panelSoft/50 px-3 py-2">
                  <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.2em] text-slate-500">
                    <span>{item.type}</span>
                    <span>{item.ts}</span>
                  </div>
                  <div className="text-slate-200">
                    {item.strategy_key} {item.symbol} • {item.short_message}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <Card>
          <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <CardTitle>Evals</CardTitle>
            <div className="flex flex-wrap gap-2 text-sm">
              <button
                className={
                  filter === "active"
                    ? "rounded-full border border-neon/60 bg-neon/10 px-3 py-1 text-neon"
                    : "rounded-full border border-border/70 px-3 py-1 text-slate-500 hover:text-slate-100"
                }
                onClick={() => setFilter("active")}
              >
                Active
              </button>
              <button
                className={
                  filter === "passed"
                    ? "rounded-full border border-neon/60 bg-neon/10 px-3 py-1 text-neon"
                    : "rounded-full border border-border/70 px-3 py-1 text-slate-500 hover:text-slate-100"
                }
                onClick={() => setFilter("passed")}
              >
                Passed
              </button>
              <button
                className={
                  filter === "failed"
                    ? "rounded-full border border-neon/60 bg-neon/10 px-3 py-1 text-neon"
                    : "rounded-full border border-border/70 px-3 py-1 text-slate-500 hover:text-slate-100"
                }
                onClick={() => setFilter("failed")}
              >
                Failed
              </button>
              <button
                className={
                  filter === "archived"
                    ? "rounded-full border border-neon/60 bg-neon/10 px-3 py-1 text-neon"
                    : "rounded-full border border-border/70 px-3 py-1 text-slate-500 hover:text-slate-100"
                }
                onClick={() => setFilter("archived")}
              >
                Archived
              </button>
            </div>
            {!Object.keys(prices).length ? <Skeleton className="h-5 w-24" /> : null}
          </CardHeader>
          <CardContent>
            <div className="mb-3 text-xs text-slate-500 md:hidden">Swipe to view all columns.</div>
            <EvalsTable evals={filteredEvals} />
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
