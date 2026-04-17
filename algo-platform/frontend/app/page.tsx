"use client";

import { useEffect, useMemo, useState } from "react";
import { PriceCard } from "@/components/PriceCard";
import { EvalsTable } from "@/components/EvalsTable";
import { NewEvalModal } from "@/components/NewEvalModal";
import { StrategyList } from "@/components/StrategyList";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useRealtime } from "@/lib/realtime";
import { useRealtimeStore } from "@/lib/store";
import { exchangeFeedLabel, tradingviewTickerForInstrument, type MatrixInstrument } from "@/lib/instruments";
import type { StrategySummary } from "@/lib/strategies";

type TabKey = "strategies" | "evals";

export default function DashboardPage() {
  const prices = useRealtimeStore((s) => s.prices);
  const setPrices = useRealtimeStore((s) => s.setPrices);
  const setEvals = useRealtimeStore((s) => s.setEvals);
  const evals = useRealtimeStore((s) => Object.values(s.evals));
  const wsConnected = useRealtimeStore((s) => s.wsConnected);
  const [tab, setTab] = useState<TabKey>("strategies");
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const [instruments, setInstruments] = useState<MatrixInstrument[]>([]);

  useRealtime();

  useEffect(() => {
    const load = async () => {
      const [pricesRes, evalsRes, strategiesRes, instrumentsRes] = await Promise.all([
        fetch("/api/prices"),
        fetch("/api/evals"),
        fetch("/api/strategies"),
        fetch("/api/market-data/matrix"),
      ]);
      if (pricesRes.ok) {
        setPrices(await pricesRes.json());
      }
      if (evalsRes.ok) {
        setEvals(await evalsRes.json());
      }
      if (strategiesRes.ok) {
        setStrategies(await strategiesRes.json());
      }
      if (instrumentsRes.ok) {
        setInstruments(await instrumentsRes.json());
      }
    };
    load();
  }, [setPrices, setEvals]);

  const activeEvals = useMemo(
    () => evals.filter((row) => row.status === "ACTIVE"),
    [evals]
  );

  const activeEvalCounts = useMemo(() => {
    return activeEvals.reduce<Record<string, number>>((acc, row) => {
      acc[row.strategy_key] = (acc[row.strategy_key] ?? 0) + 1;
      return acc;
    }, {});
  }, [activeEvals]);

  const instrumentById = useMemo(
    () => Object.fromEntries(instruments.map((instrument) => [instrument.instrument_id, instrument])),
    [instruments]
  );

  const featuredSymbols = useMemo(() => {
    const activeSymbols = activeEvals.map((row) => row.symbol);
    const priority = ["BTC", "ETH", "SOL", ...activeSymbols];
    const unique = Array.from(new Set(priority)).filter((symbol) => prices[symbol] != null);
    if (unique.length >= 3) return unique.slice(0, 3);
    const liveSymbols = Object.keys(prices);
    return [...unique, ...liveSymbols.filter((symbol) => !unique.includes(symbol))].slice(0, 3);
  }, [activeEvals, prices]);

  const handleStrategyCreated = (strategy: StrategySummary) => {
    setStrategies((current) => [strategy, ...current.filter((item) => item.key !== strategy.key)]);
  };

  const handleStrategyUpdated = (strategy: StrategySummary) => {
    setStrategies((current) =>
      current.map((item) => (item.key === strategy.key ? strategy : item))
    );
  };

  const tabClass = (value: TabKey) =>
    value === tab
      ? "rounded-full border border-neon/60 bg-neon/10 px-4 py-2 text-sm text-neon"
      : "rounded-full border border-border/70 px-4 py-2 text-sm text-slate-500 hover:text-slate-100";

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.4em] text-neonSoft">Control Surface</p>
          <h2 className="text-2xl font-semibold text-slate-100">Strategies first, sim accounts second</h2>
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>Prices stream live while strategy routing stays explicit.</span>
            <Badge variant={wsConnected ? "success" : "warning"}>
              {wsConnected ? "Connected" : "Polling"}
            </Badge>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button className={tabClass("strategies")} onClick={() => setTab("strategies")}>
            Strategy List
          </button>
          <button className={tabClass("evals")} onClick={() => setTab("evals")}>
            Sim Account List
          </button>
          <NewEvalModal strategies={strategies} />
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {featuredSymbols.length ? (
          featuredSymbols.map((symbol) => (
            <PriceCard
              key={symbol}
              symbol={instrumentById[symbol] ? tradingviewTickerForInstrument(instrumentById[symbol]) : symbol}
              price={prices[symbol]?.price}
              ts={prices[symbol]?.ts}
              subtitle={instrumentById[symbol] ? exchangeFeedLabel(instrumentById[symbol]) : undefined}
            />
          ))
        ) : (
          <Card className="md:col-span-3">
            <CardContent className="pt-6 text-sm text-slate-500">
              Waiting for live prices...
            </CardContent>
          </Card>
        )}
      </section>

      <section>
        {tab === "strategies" ? (
          <StrategyList
            strategies={strategies}
            activeEvalCounts={activeEvalCounts}
            onCreated={handleStrategyCreated}
            onUpdated={handleStrategyUpdated}
          />
        ) : (
          <Card>
            <CardContent className="pt-5">
              <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-neonSoft">Active Sim Accounts</p>
                  <h2 className="text-2xl font-semibold text-slate-100">Only live sim accounts stay here</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Archived, failed, and passed runs are out of the main list. This view is for the sim accounts that are active right now.
                  </p>
                </div>
                <div className="rounded-lg border border-border/60 bg-panelSoft/60 px-4 py-2 text-sm text-slate-300">
                  Active sim account count: {activeEvals.length}
                </div>
              </div>
              <div className="mb-3 text-xs text-slate-500 md:hidden">Swipe to view all columns.</div>
              <EvalsTable evals={activeEvals} />
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  );
}
