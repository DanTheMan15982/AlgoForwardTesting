"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { PriceCard } from "@/components/PriceCard";
import { EvalsTable } from "@/components/EvalsTable";
import { NewEvalModal } from "@/components/NewEvalModal";
import { StrategyList } from "@/components/StrategyList";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatCurrency, formatPercent } from "@/lib/format";
import { useRealtime } from "@/lib/realtime";
import { useRealtimeStore } from "@/lib/store";
import type { StrategySummary } from "@/lib/strategies";

type ScreenKey = "overview" | "strategies" | "accounts" | "backtesting";

export default function DashboardPage() {
  const router = useRouter();
  const prices = useRealtimeStore((s) => s.prices);
  const setPrices = useRealtimeStore((s) => s.setPrices);
  const setEvals = useRealtimeStore((s) => s.setEvals);
  const evals = useRealtimeStore((s) => Object.values(s.evals));
  const wsConnected = useRealtimeStore((s) => s.wsConnected);
  const [screen, setScreen] = useState<ScreenKey>("overview");
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const [accountsSearch, setAccountsSearch] = useState("");

  useRealtime();

  useEffect(() => {
    const load = async () => {
      const [pricesRes, evalsRes, strategiesRes] = await Promise.all([
        fetch("/api/prices"),
        fetch("/api/evals"),
        fetch("/api/strategies"),
      ]);
      if (pricesRes.ok) setPrices(await pricesRes.json());
      if (evalsRes.ok) setEvals(await evalsRes.json());
      if (strategiesRes.ok) setStrategies(await strategiesRes.json());
    };
    load();
  }, [setPrices, setEvals]);

  const activeEvals = useMemo(() => evals.filter((row) => row.status === "ACTIVE"), [evals]);

  const activeEvalCounts = useMemo(() => {
    return activeEvals.reduce<Record<string, number>>((acc, row) => {
      acc[row.strategy_key] = (acc[row.strategy_key] ?? 0) + 1;
      return acc;
    }, {});
  }, [activeEvals]);

  const totalAccounts = evals.length;
  const pausedAccounts = evals.filter((row) => row.status === "PAUSED").length;
  const failedAccounts = evals.filter((row) => row.status === "FAILED").length;
  const passedAccounts = evals.filter((row) => row.status === "PASSED").length;
  const openPositions = activeEvals.filter((row) => row.has_open_position).length;
  const openTradesTotal = activeEvals.reduce((sum, row) => {
    if (Array.isArray(row.open_positions) && row.open_positions.length) return sum + row.open_positions.length;
    return sum + (row.has_open_position ? 1 : 0);
  }, 0);
  const liveStrategyCoverage = new Set(activeEvals.map((row) => row.strategy_key)).size;

  const totalOpenPnl = activeEvals.reduce((sum, row) => sum + (row.open_pnl ?? 0), 0);
  const totalPnl = evals.reduce((sum, row) => sum + (row.current_equity - row.starting_balance), 0);
  const totalWins = evals.reduce((sum, row) => sum + (row.wins ?? 0), 0);
  const totalLosses = evals.reduce((sum, row) => sum + (row.losses ?? 0), 0);

  const liveSymbols = useMemo(() => {
    const keys = Object.keys(prices);
    const pickSymbol = (base: "BTC" | "ETH" | "SOL") => {
      const preferred = [base, `${base}USD`, `${base}USDT`, `${base}-USD`, `${base}USD.P`, `${base}USDT.P`];
      for (const symbol of preferred) {
        if (prices[symbol]?.price != null) return symbol;
      }
      const prefixed = keys.find((symbol) => symbol.startsWith(base) && prices[symbol]?.price != null);
      return prefixed ?? base;
    };
    return [pickSymbol("BTC"), pickSymbol("ETH"), pickSymbol("SOL")];
  }, [prices]);

  const topAccounts = useMemo(() => {
    return [...evals]
      .sort((a, b) => (b.open_pnl ?? 0) - (a.open_pnl ?? 0))
      .slice(0, 5);
  }, [evals]);

  const strategyPerformance = useMemo(() => {
    const aggregate = new Map<string, {
      key: string;
      name: string;
      activeAccounts: number;
      totalAccounts: number;
      pnl: number;
      totalPnl: number;
      wins: number;
      losses: number;
      profitFactorSum: number;
      profitFactorCount: number;
    }>();

    for (const row of evals) {
      const key = row.strategy_key;
      const existing = aggregate.get(key) ?? {
        key,
        name: strategies.find((item) => item.key === key)?.name ?? key,
        activeAccounts: 0,
        totalAccounts: 0,
        pnl: 0,
        totalPnl: 0,
        wins: 0,
        losses: 0,
        profitFactorSum: 0,
        profitFactorCount: 0,
      };
      existing.totalAccounts += 1;
      if (row.status === "ACTIVE") existing.activeAccounts += 1;
      existing.pnl += row.open_pnl ?? 0;
      existing.totalPnl += row.current_equity - row.starting_balance;
      existing.wins += row.wins ?? 0;
      existing.losses += row.losses ?? 0;
      if (row.profit_factor != null) {
        existing.profitFactorSum += row.profit_factor;
        existing.profitFactorCount += 1;
      }
      aggregate.set(key, existing);
    }

    return [...aggregate.values()].map((item) => {
      const totalDecisions = item.wins + item.losses;
      return {
        ...item,
        winRate: totalDecisions > 0 ? item.wins / totalDecisions : null,
        avgProfitFactor: item.profitFactorCount > 0 ? item.profitFactorSum / item.profitFactorCount : null,
      };
    });
  }, [evals, strategies]);

  const topStrategyCards = useMemo(
    () =>
      [...strategyPerformance]
        .filter((item) => item.winRate != null)
        .sort((a, b) => b.totalPnl - a.totalPnl)
        .slice(0, 3),
    [strategyPerformance]
  );

  const topStrategiesByPnl = useMemo(
    () => [...strategyPerformance].sort((a, b) => b.pnl - a.pnl).slice(0, 5),
    [strategyPerformance]
  );

  const topStrategiesByWinRate = useMemo(
    () =>
      [...strategyPerformance]
        .filter((item) => item.wins + item.losses >= 5 && item.winRate != null)
        .sort((a, b) => (b.winRate ?? 0) - (a.winRate ?? 0))
        .slice(0, 5),
    [strategyPerformance]
  );

  const visibleActiveEvals = useMemo(() => {
    const normalized = accountsSearch.trim().toLowerCase();
    if (!normalized) return activeEvals;
    return activeEvals.filter((row) => {
      return (
        row.name.toLowerCase().includes(normalized) ||
        row.symbol.toLowerCase().includes(normalized) ||
        row.strategy_key.toLowerCase().includes(normalized) ||
        (row.strategy_name?.toLowerCase().includes(normalized) ?? false) ||
        row.status.toLowerCase().includes(normalized)
      );
    });
  }, [accountsSearch, activeEvals]);

  const handleStrategyCreated = (strategy: StrategySummary) => {
    setStrategies((current) => [strategy, ...current.filter((item) => item.key !== strategy.key)]);
  };

  const handleStrategyUpdated = (strategy: StrategySummary) => {
    setStrategies((current) => current.map((item) => (item.key === strategy.key ? strategy : item)));
  };

  const screenButtonClass = (value: ScreenKey) =>
    value === screen ? "dash-chip dash-chip-active" : "dash-chip";

  return (
    <div className="space-y-8">
      <section className="dash-hero">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-neonSoft">Dashboard</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-100">Operations Center</h2>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-400">
            <Badge variant={wsConnected ? "success" : "warning"}>
              {wsConnected ? "Realtime Connected" : "Polling Fallback"}
            </Badge>
            <span>{activeEvals.length} live / {totalAccounts} total accounts</span>
          </div>
        </div>
      </section>

      <section className="flex flex-wrap gap-2">
        <button className={screenButtonClass("overview")} onClick={() => setScreen("overview")}>Overview</button>
        <button className={screenButtonClass("strategies")} onClick={() => setScreen("strategies")}>Strategies</button>
        <button className={screenButtonClass("accounts")} onClick={() => setScreen("accounts")}>Accounts</button>
        <button className={screenButtonClass("backtesting")} onClick={() => setScreen("backtesting")}>Backtesting</button>
      </section>

      {screen === "overview" ? (
        <section className="space-y-6">
          <div className="grid gap-4 lg:grid-cols-4">
            <MetricCard label="Live Accounts" value={activeEvals.length} tone="market" />
            <MetricCard label="Total P/L" value={formatCurrency(totalPnl)} tone={totalPnl >= 0 ? "perf" : "risk"} />
            <MetricCard label="Open Trades" value={openTradesTotal} tone="perf" />
            <MetricCard label="Strategies Live" value={liveStrategyCoverage} tone="market" />
          </div>

          <div className="grid gap-4 lg:grid-cols-4">
            <MiniStat label="Total Accounts" value={totalAccounts} tone="market" />
            <MiniStat label="Open Positions" value={openPositions} tone="perf" />
            <MiniStat label="Wins" value={totalWins} tone="perf" />
            <MiniStat label="Losses" value={totalLosses} tone="risk" />
          </div>

          <Card className="dash-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-100">Top 3 Strategies</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-3">
                {topStrategyCards.length ? topStrategyCards.map((item) => (
                  <div key={item.key} className="dash-row">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-slate-100">{item.name}</div>
                      <div className="text-xs text-slate-500">
                        WR {item.winRate != null ? formatPercent(item.winRate) : "--"}
                      </div>
                    </div>
                    <div className={`tabular text-sm font-semibold ${item.totalPnl >= 0 ? "text-success" : "text-danger"}`}>
                      {formatCurrency(item.totalPnl)}
                    </div>
                  </div>
                )) : (
                  <div className="text-sm text-slate-500">No strategy performance yet.</div>
                )}
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 xl:grid-cols-5">
            <div className="space-y-4 xl:col-span-3">
              <Card className="dash-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-slate-100">Market Pulse</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-3">
                    {liveSymbols.map((symbol) => (
                      <PriceCard
                        key={symbol}
                        symbol={symbol}
                        price={prices[symbol]?.price}
                        ts={prices[symbol]?.ts}
                        subtitle="Live"
                      />
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card className="dash-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-slate-100">Activity Snapshot</CardTitle>
                </CardHeader>
                <CardContent>
                  {topAccounts.length ? (
                    <div className="space-y-2">
                      {topAccounts.map((row) => {
                        const pnl = row.open_pnl ?? 0;
                        return (
                          <button
                            key={row.id}
                            type="button"
                            onClick={() => router.push(`/evals/${row.id}`)}
                            className="dash-row w-full text-left"
                          >
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium text-slate-100">{row.name}</div>
                              <div className="text-xs text-slate-500">
                                {row.strategy_name || row.strategy_key} • {row.status}
                              </div>
                            </div>
                            <div className={`tabular text-sm font-semibold ${pnl >= 0 ? "text-success" : "text-danger"}`}>
                              {formatCurrency(pnl)}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-sm text-slate-500">No active accounts.</div>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="space-y-4 xl:col-span-2">
              <Card className="dash-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-slate-100">Account Outcomes</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-3">
                  <MiniStat label="Active" value={activeEvals.length} tone="perf" />
                  <MiniStat label="Paused" value={pausedAccounts} tone="risk" />
                  <MiniStat label="Passed" value={passedAccounts} tone="market" />
                  <MiniStat label="Failed" value={failedAccounts} tone="risk" />
                  <MiniStat label="Open P/L" value={formatCurrency(totalOpenPnl)} tone={totalOpenPnl >= 0 ? "perf" : "risk"} />
                </CardContent>
              </Card>

              <Card className="dash-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-slate-100">Top Strategies by Open P/L</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {topStrategiesByPnl.length ? topStrategiesByPnl.map((item) => (
                      <div key={item.key} className="dash-row">
                        <div className="min-w-0">
                          <div className="truncate text-sm text-slate-200">{item.name}</div>
                          <div className="text-xs text-slate-500">
                            {item.activeAccounts} live • WR {item.winRate != null ? formatPercent(item.winRate) : "--"}
                          </div>
                        </div>
                        <div className={`tabular text-sm font-semibold ${item.pnl >= 0 ? "text-success" : "text-danger"}`}>
                          {formatCurrency(item.pnl)}
                        </div>
                      </div>
                    )) : (
                      <div className="text-sm text-slate-500">No strategy data yet.</div>
                    )}
                  </div>
                </CardContent>
              </Card>

              <Card className="dash-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-slate-100">Top Strategies by Win Rate</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {topStrategiesByWinRate.length ? topStrategiesByWinRate.map((item) => (
                      <div key={item.key} className="dash-row">
                        <div className="min-w-0">
                          <div className="truncate text-sm text-slate-200">{item.name}</div>
                          <div className="text-xs text-slate-500">
                            {item.wins}W-{item.losses}L • PF {item.avgProfitFactor != null ? item.avgProfitFactor.toFixed(2) : "--"}
                          </div>
                        </div>
                        <div className="tabular text-sm font-semibold text-neon">
                          {item.winRate != null ? formatPercent(item.winRate) : "--"}
                        </div>
                      </div>
                    )) : (
                      <div className="text-sm text-slate-500">Need at least 5 decided trades per strategy.</div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </section>
      ) : null}

      {screen === "strategies" ? (
        <section className="space-y-4">
          <Card className="dash-card">
            <CardContent className="pt-5">
              <StrategyList
                strategies={strategies}
                activeEvalCounts={activeEvalCounts}
                onCreated={handleStrategyCreated}
                onUpdated={handleStrategyUpdated}
              />
            </CardContent>
          </Card>
        </section>
      ) : null}

      {screen === "accounts" ? (
        <section>
          <Card className="dash-card">
            <CardContent className="pt-5">
              <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-neonSoft">Accounts</p>
                  <h2 className="text-2xl font-semibold text-slate-100">Live Sim Accounts</h2>
                </div>
                <div className="flex items-center gap-3">
                  <div className="rounded-lg border border-border/60 bg-panelSoft/60 px-4 py-2 text-sm text-slate-300">
                    Active: {activeEvals.length}
                  </div>
                  <NewEvalModal strategies={strategies} />
                </div>
              </div>
              <div className="mb-4 flex flex-col gap-3 rounded-xl border border-border/70 bg-panelSoft/50 p-3 sm:flex-row sm:items-center sm:justify-between">
                <Input
                  value={accountsSearch}
                  placeholder="Search account, strategy, or ticker..."
                  onChange={(event) => setAccountsSearch(event.target.value)}
                  className="sm:max-w-md"
                />
                <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  {visibleActiveEvals.length} shown
                </div>
              </div>
              <EvalsTable evals={visibleActiveEvals} />
            </CardContent>
          </Card>
        </section>
      ) : null}

      {screen === "backtesting" ? (
        <section>
          <Card className="dash-card">
            <CardContent className="pt-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-neonSoft">Backtesting</p>
                  <h2 className="text-2xl font-semibold text-slate-100">Research Workspace</h2>
                  <p className="mt-2 max-w-xl text-sm text-slate-400">
                    Historical analytics, parameter sweeps, and strategy comparison will live here.
                  </p>
                </div>
                <button
                  type="button"
                  className="dash-chip dash-chip-active"
                  onClick={() => router.push("/backtesting")}
                >
                  Open Backtesting Page
                </button>
              </div>
            </CardContent>
          </Card>
        </section>
      ) : null}
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: "market" | "perf" | "risk";
}) {
  return (
    <Card className={`dash-card dash-card-${tone}`}>
      <CardContent className="space-y-2 p-5">
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{label}</div>
        <div className="tabular text-3xl font-semibold text-slate-100">{value}</div>
      </CardContent>
    </Card>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: "market" | "perf" | "risk";
}) {
  return (
    <div className={`dash-mini dash-mini-${tone}`}>
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="tabular mt-2 text-2xl font-semibold text-slate-100">{value}</div>
    </div>
  );
}
