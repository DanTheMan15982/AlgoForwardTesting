"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { formatCurrency, formatPercent } from "@/lib/format";

type AnalysisResponse = {
  file_name: string;
  params: {
    starting_balance: number;
    max_dd_pct: number;
    daily_dd_pct: number;
    profit_target_pct: number;
    monte_carlo_runs: number;
  };
  result: {
    trades_total: number;
    wins: number;
    losses: number;
    win_rate: number | null;
    net_pnl: number;
    avg_pnl_per_trade: number;
    equity_curve: number[];
    drawdown_curve: number[];
    start_index_stats: {
      pass_rate: number;
      fail_rate: number;
      unresolved_rate: number;
      median_trades_to_resolution: number | null;
      samples: Array<{
        start_trade_no: number;
        start_ts: string;
        result: string;
        final_equity: number;
        max_drawdown_pct: number;
        resolved_trade_count: number | null;
      }>;
    };
    monte_carlo: {
      runs: number;
      pass_rate: number;
      fail_rate: number;
      unresolved_rate: number;
      final_equity_median: number;
      final_equity_min: number;
      final_equity_max: number;
      max_drawdown_median: number;
      p10_curve: number[];
      p50_curve: number[];
      p90_curve: number[];
    };
    survivability: Array<{
      horizon_trades: number;
      survival_rate: number;
    }>;
  };
};

export default function BacktestingPage() {
  const [file, setFile] = useState<File | null>(null);
  const [startingBalance, setStartingBalance] = useState("10000");
  const [maxDdPct, setMaxDdPct] = useState("0.06");
  const [dailyDdPct, setDailyDdPct] = useState("0.03");
  const [profitTargetPct, setProfitTargetPct] = useState("0.08");
  const [mcRuns, setMcRuns] = useState("2000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AnalysisResponse | null>(null);

  const topStartSamples = useMemo(
    () => data?.result.start_index_stats.samples.slice(0, 10) ?? [],
    [data]
  );

  const handleAnalyze = async () => {
    setError(null);
    if (!file) {
      setError("Please upload a CSV file.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("starting_balance", startingBalance);
    form.append("max_dd_pct", maxDdPct);
    form.append("daily_dd_pct", dailyDdPct);
    form.append("profit_target_pct", profitTargetPct);
    form.append("monte_carlo_runs", mcRuns);

    setLoading(true);
    try {
      const res = await fetch("/api/backtesting/analyze", { method: "POST", body: form });
      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        setError(payload?.reason ?? "Failed to analyze CSV.");
        return;
      }
      setData(await res.json());
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <section>
        <p className="text-xs uppercase tracking-[0.35em] text-neonSoft">Backtesting</p>
        <h2 className="text-2xl font-semibold text-slate-100">CSV Simulation Lab</h2>
      </section>

      <Card className="dash-card">
        <CardHeader>
          <CardTitle>Upload TradingView CSV</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <input
            type="file"
            accept=".csv,text/csv"
            className="rounded-lg border border-border/70 bg-panelSoft/70 px-3 py-2 text-sm text-slate-200"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <div className="grid gap-3 md:grid-cols-5">
            <Input value={startingBalance} onChange={(e) => setStartingBalance(e.target.value)} placeholder="Starting balance" />
            <Input value={maxDdPct} onChange={(e) => setMaxDdPct(e.target.value)} placeholder="Max DD (0.06)" />
            <Input value={dailyDdPct} onChange={(e) => setDailyDdPct(e.target.value)} placeholder="Daily DD (0.03)" />
            <Input value={profitTargetPct} onChange={(e) => setProfitTargetPct(e.target.value)} placeholder="Profit target (0.08)" />
            <Input value={mcRuns} onChange={(e) => setMcRuns(e.target.value)} placeholder="Monte Carlo runs" />
          </div>
          {error ? <div className="text-sm text-danger">{error}</div> : null}
          <div>
            <Button onClick={handleAnalyze} disabled={loading || !file}>
              {loading ? "Analyzing..." : "Run Analysis"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {data ? (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-5">
            <StatCard label="Trades" value={String(data.result.trades_total)} />
            <StatCard label="Net P/L" value={formatCurrency(data.result.net_pnl)} />
            <StatCard label="Win Rate" value={data.result.win_rate != null ? formatPercent(data.result.win_rate) : "--"} />
            <StatCard label="Pass Rate (Any Start)" value={formatPercent(data.result.start_index_stats.pass_rate)} />
            <StatCard label="MC Pass Rate" value={formatPercent(data.result.monte_carlo.pass_rate)} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="dash-card">
              <CardHeader><CardTitle>Equity Curve</CardTitle></CardHeader>
              <CardContent>
                <LineChart values={data.result.equity_curve} color="#00f0ff" />
              </CardContent>
            </Card>
            <Card className="dash-card">
              <CardHeader><CardTitle>Drawdown Curve</CardTitle></CardHeader>
              <CardContent>
                <LineChart values={data.result.drawdown_curve} color="#f59e0b" />
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="dash-card">
              <CardHeader><CardTitle>Monte Carlo Envelope</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <LineChart values={data.result.monte_carlo.p10_curve} color="#f43f5e" />
                <LineChart values={data.result.monte_carlo.p50_curve} color="#00f0ff" />
                <LineChart values={data.result.monte_carlo.p90_curve} color="#22c55e" />
                <div className="grid gap-2 text-xs text-slate-400 md:grid-cols-2">
                  <div>Median Final Equity: {formatCurrency(data.result.monte_carlo.final_equity_median)}</div>
                  <div>Median Max DD: {formatPercent(data.result.monte_carlo.max_drawdown_median)}</div>
                </div>
              </CardContent>
            </Card>

            <Card className="dash-card">
              <CardHeader><CardTitle>Survivability</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {data.result.survivability.map((item) => (
                  <div key={item.horizon_trades} className="dash-row">
                    <div className="text-sm text-slate-300">Survive {item.horizon_trades} trades</div>
                    <div className="tabular text-sm font-semibold text-neon">{formatPercent(item.survival_rate)}</div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          <Card className="dash-card">
            <CardHeader><CardTitle>Start-Trade Simulation Samples</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2">
                {topStartSamples.map((sample) => (
                  <div key={`${sample.start_trade_no}-${sample.start_ts}`} className="dash-row">
                    <div className="text-sm text-slate-300">
                      Trade #{sample.start_trade_no} • {sample.result}
                    </div>
                    <div className="tabular text-sm text-slate-100">
                      {formatCurrency(sample.final_equity)}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card className="dash-card">
      <CardContent className="space-y-1 p-4">
        <div className="text-xs uppercase tracking-[0.22em] text-slate-500">{label}</div>
        <div className="tabular text-2xl font-semibold text-slate-100">{value}</div>
      </CardContent>
    </Card>
  );
}

function LineChart({ values, color }: { values: number[]; color: string }) {
  const width = 760;
  const height = 180;
  if (!values.length) {
    return <div className="text-sm text-slate-500">No data.</div>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1e-9, max - min);
  const points = values
    .map((value, idx) => {
      const x = (idx / Math.max(1, values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-44 w-full rounded-md border border-border/70 bg-panelSoft/60">
      <polyline fill="none" stroke={color} strokeWidth="2.25" points={points} />
    </svg>
  );
}
