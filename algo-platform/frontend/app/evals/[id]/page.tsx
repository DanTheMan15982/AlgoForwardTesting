"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/StatCard";
import { TradeTable, TradeRow } from "@/components/TradeTable";
import { EventList } from "@/components/EventList";
import { formatCountdown, formatCurrency, formatPercent } from "@/lib/format";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useFlashDelta } from "@/lib/useFlashDelta";

type EvalDetail = {
  id: string;
  name: string;
  status: string;
  symbol: string;
  strategy_key: string;
  strategy_name?: string | null;
  starting_balance: number;
  current_balance: number;
  current_equity: number;
  day_start_equity: number;
  max_dd_pct: number;
  daily_dd_pct: number;
  dynamic_tp_enabled?: boolean;
  webhook_passthrough_enabled?: boolean;
  webhook_passthrough_url?: string | null;
  daily_dd_guard_enabled?: boolean;
  daily_dd_guard_risk_multiple?: number;
  daily_dd_guard_buffer_pct?: number;
  daily_dd_guard_buffer_usd?: number;
  daily_dd_guard_auto_resume_on_daily_reset?: boolean;
  daily_dd_guard_close_open_positions_on_trigger?: boolean;
  daily_dd_guard_blocking?: boolean;
  daily_dd_guard_reason?: string | null;
  daily_dd_guard_threshold_usd?: number | null;
  daily_dd_remaining_usd?: number | null;
  daily_dd_guard_blocks_entries_until?: string | null;
  last_price?: number | null;
  open_pnl?: number | null;
  unrealized_equity?: number | null;
  daily_reset_at_ts?: string | null;
  daily_reset_seconds_remaining?: number | null;
  risk_usd?: number | null;
  average_rr?: number | null;
  fees_enabled?: boolean;
  slippage_enabled?: boolean;
  taker_fee_rate?: number;
  slippage_min_usd?: number;
  slippage_max_usd?: number;
  latency_enabled?: boolean;
  latency_min_sec?: number;
  latency_max_sec?: number;
  total_fees_paid?: number | null;
  total_slippage_impact?: number | null;
  profit_target_pct?: number | null;
  profit_target_equity?: number | null;
  profit_remaining_usd?: number | null;
  profit_progress_pct?: number | null;
  avg_win_r?: number | null;
  win_rate_r?: number | null;
  n_valid_r?: number | null;
  n_wins_r?: number | null;
  expectancy_r?: number | null;
  passed_at?: string | null;
  archived_at?: string | null;
  wins?: number | null;
  losses?: number | null;
  breakeven?: number | null;
  win_rate_pct?: number | null;
  profit_factor?: number | null;
  avg_win?: number | null;
  avg_loss?: number | null;
  rolling_net_pnl?: number | null;
  rolling_avg_pnl_per_trade?: number | null;
  rolling_win_rate?: number | null;
  rolling_profit_factor?: number | null;
  rolling_avg_win?: number | null;
  rolling_avg_loss?: number | null;
  expected_trades_to_pass?: number | null;
  expected_days_to_pass?: number | null;
  expected_trades_to_daily_fail?: number | null;
  expected_trades_to_max_fail?: number | null;
  open_position?: {
    id: string;
    symbol: string;
    side: string;
    qty: number;
    entry_price: number;
    stop_price: number;
    tp_price: number | null;
    opened_at: string;
    status: string;
    rr?: number | null;
    entry_fee?: number | null;
    exit_fee?: number | null;
    total_fees?: number | null;
    entry_slippage?: number | null;
    exit_slippage?: number | null;
    entry_fill_price?: number | null;
    exit_fill_price?: number | null;
  } | null;
  open_positions?: Array<{
    id: string;
    symbol: string;
    side: string;
    qty: number;
    entry_price: number;
    stop_price: number;
    tp_price: number | null;
    opened_at: string;
    status: string;
    rr?: number | null;
    entry_fee?: number | null;
    exit_fee?: number | null;
    total_fees?: number | null;
    entry_slippage?: number | null;
    exit_slippage?: number | null;
    entry_fill_price?: number | null;
    exit_fill_price?: number | null;
  }>;
};

type EventItem = {
  id: string;
  ts: string;
  type: string;
  payload: Record<string, unknown>;
};

type OpenPosition = NonNullable<EvalDetail["open_positions"]>[number];

type EquityPoint = {
  ts: string;
  equity: number;
  drawdown_pct: number;
  daily_dd_limit_equity: number;
  max_dd_limit_equity: number;
};

type OpenPositionRowProps = {
  position: OpenPosition;
  lastPrice: number | null;
  onSelect: (position: OpenPosition) => void;
  isActive: boolean;
};

function OpenPositionRow({ position, lastPrice, onSelect, isActive }: OpenPositionRowProps) {
  const entryFill = position.entry_fill_price ?? position.entry_price;
  const openPnl =
    lastPrice != null
      ? position.side === "LONG"
        ? (lastPrice - entryFill) * position.qty
        : (entryFill - lastPrice) * position.qty
      : null;
  const risk = Math.abs(position.entry_price - position.stop_price);
  const targetR =
    position.tp_price != null && risk > 0
      ? position.side === "LONG"
        ? (position.tp_price - position.entry_price) / risk
        : (position.entry_price - position.tp_price) / risk
      : null;
  const targetLabel =
    position.tp_price == null ? "Dynamic" : targetR != null ? targetR.toFixed(2) : "--";
  const openPnlFlash = useFlashDelta(`openpnl-${position.id}`, openPnl ?? null);
  const openPnlColor =
    openPnl == null
      ? "text-slate-400"
      : openPnl > 0
        ? "text-success"
        : openPnl < 0
          ? "text-danger"
          : "text-slate-400";
  const flashClass =
    openPnlFlash.flash
      ? openPnlFlash.direction === "up"
        ? "text-success"
        : "text-danger"
      : openPnlColor;
  const haloClass =
    isActive && position.side === "LONG"
      ? "halo-long"
      : isActive && position.side === "SHORT"
        ? "halo-short"
        : "";

  return (
    <tr
      onClick={() => onSelect(position)}
      className={`cursor-pointer border-b border-border/60 bg-panel/60 transition-colors hover:bg-panelSoft/80 hover:shadow-glowSoft ${haloClass}`}
    >
      <td className="px-3 py-2 text-left">
        <Badge variant={position.side === "LONG" ? "success" : "danger"}>
          {position.side}
        </Badge>
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{position.qty.toFixed(4)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(position.entry_price)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(position.stop_price)}</td>
      <td className="px-3 py-2 text-right">
        {position.tp_price == null ? (
          <Badge variant="magenta">Dynamic</Badge>
        ) : (
          <span className="tabular-nums text-neonSoft">{targetLabel}</span>
        )}
      </td>
      <td
        className={`px-3 py-2 text-right tabular-nums transition-colors duration-700 ease-out ${flashClass}`}
      >
        {openPnl != null ? formatCurrency(openPnl) : "--"}
      </td>
    </tr>
  );
}

type EquityDrawdownChartProps = {
  series: EquityPoint[];
};

function EquityDrawdownChart({ series }: EquityDrawdownChartProps) {
  if (series.length < 2) {
    return <div className="text-sm text-slate-500">Not enough data.</div>;
  }
  const width = 1000;
  const height = 240;
  const padding = 24;
  const usableHeight = height - padding * 2;
  const eqValues = series.map((point) => point.equity);
  const minEq = Math.min(...eqValues);
  const maxEq = Math.max(...eqValues);
  const eqRange = Math.max(1, maxEq - minEq);
  const maxDrawdown = Math.max(0.001, ...series.map((point) => point.drawdown_pct));
  const lastPoint = series[series.length - 1];

  const toX = (index: number) =>
    padding + (index / (series.length - 1)) * (width - padding * 2);
  const toEqY = (value: number) =>
    padding + ((maxEq - value) / eqRange) * usableHeight;
  const toDdY = (value: number) =>
    padding + (1 - value / maxDrawdown) * usableHeight;

  const eqPath = series
    .map((point, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toEqY(point.equity)}`)
    .join(" ");
  const ddPath = series
    .map((point, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toDdY(point.drawdown_pct)}`)
    .join(" ");

  const dailyLimitY = toEqY(lastPoint.daily_dd_limit_equity);
  const maxLimitY = toEqY(lastPoint.max_dd_limit_equity);

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="h-2 w-6 rounded-full bg-neon/70" />
          Equity
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-6 rounded-full bg-neonMagenta/60" />
          Drawdown
        </div>
        <div className="flex items-center gap-2">
          <span className="h-[2px] w-6 border-t border-dashed border-warn/70" />
          Daily DD limit
        </div>
        <div className="flex items-center gap-2">
          <span className="h-[2px] w-6 border-t border-dashed border-danger/70" />
          Max DD limit
        </div>
      </div>
      <svg
        className="mt-3 h-[220px] w-full"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
      >
        <path
          d={eqPath}
          className="fill-none stroke-neon stroke-[2]"
        />
        <path
          d={ddPath}
          className="fill-none stroke-neonMagenta stroke-[1.5]"
        />
        <line
          x1={padding}
          x2={width - padding}
          y1={dailyLimitY}
          y2={dailyLimitY}
          className="stroke-warn/80 stroke-[1]"
          strokeDasharray="4 4"
        />
        <line
          x1={padding}
          x2={width - padding}
          y1={maxLimitY}
          y2={maxLimitY}
          className="stroke-danger/70 stroke-[1]"
          strokeDasharray="4 4"
        />
      </svg>
    </div>
  );
}

export default function EvalDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const evalId = params?.id;
  const [detail, setDetail] = useState<EvalDetail | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [equitySeries, setEquitySeries] = useState<EquityPoint[]>([]);
  const [now, setNow] = useState(Date.now());
  const [activePosition, setActivePosition] = useState<OpenPosition | null>(null);
  const [positionDialogOpen, setPositionDialogOpen] = useState(false);
  const [riskInput, setRiskInput] = useState("");
  const [profitTargetInput, setProfitTargetInput] = useState("");
  const [feeEnabled, setFeeEnabled] = useState(true);
  const [slippageEnabled, setSlippageEnabled] = useState(true);
  const [feeRateInput, setFeeRateInput] = useState("0.0004");
  const [slipMinInput, setSlipMinInput] = useState("2");
  const [slipMaxInput, setSlipMaxInput] = useState("20");
  const [latencyEnabled, setLatencyEnabled] = useState(false);
  const [latencyMinInput, setLatencyMinInput] = useState("2");
  const [latencyMaxInput, setLatencyMaxInput] = useState("10");
  const [dynamicTpEnabled, setDynamicTpEnabled] = useState(false);
  const [webhookPassthroughEnabled, setWebhookPassthroughEnabled] = useState(false);
  const [webhookPassthroughUrl, setWebhookPassthroughUrl] = useState("");
  const [webhookPassthroughDirty, setWebhookPassthroughDirty] = useState(false);
  const [dailyDdGuardEnabled, setDailyDdGuardEnabled] = useState(false);
  const [dailyDdGuardThresholdUsdInput, setDailyDdGuardThresholdUsdInput] = useState("0");
  const [dailyDdGuardAutoResume, setDailyDdGuardAutoResume] = useState(true);
  const [dailyDdGuardCloseOpen, setDailyDdGuardCloseOpen] = useState(false);
  const [dailyDdGuardDirty, setDailyDdGuardDirty] = useState(false);

  useEffect(() => {
    if (!evalId) return;
    let interval: ReturnType<typeof setInterval> | null = null;
    let cancelled = false;

    const load = async () => {
      const [detailRes, tradesRes, eventsRes, equityRes] = await Promise.all([
        fetch(`/api/evals/${evalId}`),
        fetch(`/api/evals/${evalId}/trades`),
        fetch(`/api/evals/${evalId}/events?limit=50`),
        fetch(`/api/evals/${evalId}/equity-series?limit=500`)
      ]);
      if (cancelled) return;
      if (detailRes.status === 404) {
        if (interval) clearInterval(interval);
        router.replace("/");
        return;
      }
      if (detailRes.ok) {
        setDetail(await detailRes.json());
      }
      if (tradesRes.ok) {
        setTrades(await tradesRes.json());
      }
      if (eventsRes.ok) {
        setEvents(await eventsRes.json());
      }
      if (equityRes.ok) {
        setEquitySeries(await equityRes.json());
      }
    };

    load();
    interval = setInterval(load, 5000);

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [evalId, router]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!detail) return;
    setRiskInput(detail.risk_usd?.toString() ?? "");
    if (detail.profit_target_pct != null) {
      const displayPct = detail.profit_target_pct <= 1 ? detail.profit_target_pct * 100 : detail.profit_target_pct;
      setProfitTargetInput(displayPct.toString());
    } else {
      setProfitTargetInput("");
    }
    setFeeEnabled(Boolean(detail.fees_enabled));
    setSlippageEnabled(Boolean(detail.slippage_enabled));
    setFeeRateInput((detail.taker_fee_rate ?? 0.0004).toString());
    setSlipMinInput((detail.slippage_min_usd ?? 2).toString());
    setSlipMaxInput((detail.slippage_max_usd ?? 20).toString());
    setLatencyEnabled(Boolean(detail.latency_enabled));
    setLatencyMinInput((detail.latency_min_sec ?? 2).toString());
    setLatencyMaxInput((detail.latency_max_sec ?? 10).toString());
    setDynamicTpEnabled(Boolean(detail.dynamic_tp_enabled));
    if (!webhookPassthroughDirty) {
      setWebhookPassthroughEnabled(Boolean(detail.webhook_passthrough_enabled));
      setWebhookPassthroughUrl(detail.webhook_passthrough_url ?? "");
    }
  }, [detail, webhookPassthroughDirty]);

  useEffect(() => {
    if (!detail) return;
    if (dailyDdGuardDirty) return;
    setDailyDdGuardEnabled(Boolean(detail.daily_dd_guard_enabled));
    setDailyDdGuardThresholdUsdInput((detail.daily_dd_guard_threshold_usd ?? 0).toString());
    setDailyDdGuardAutoResume(Boolean(detail.daily_dd_guard_auto_resume_on_daily_reset));
    setDailyDdGuardCloseOpen(Boolean(detail.daily_dd_guard_close_open_positions_on_trigger));
  }, [
    detail?.id,
    detail?.daily_dd_guard_enabled,
    detail?.daily_dd_guard_threshold_usd,
    detail?.daily_dd_guard_auto_resume_on_daily_reset,
    detail?.daily_dd_guard_close_open_positions_on_trigger,
    dailyDdGuardDirty
  ]);

  const pauseEval = async () => {
    if (!evalId) return;
    await fetch(`/api/evals/${evalId}/pause`, { method: "POST" });
  };

  const resumeEval = async () => {
    if (!evalId) return;
    await fetch(`/api/evals/${evalId}/resume`, { method: "POST" });
  };

  const updateRisk = async () => {
    if (!evalId) return;
    await fetch(`/api/evals/${evalId}/risk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ risk_usd: Number(riskInput) })
    });
  };

  const updateCosts = async () => {
    if (!evalId) return;
    await fetch(`/api/evals/${evalId}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fees_enabled: feeEnabled,
        slippage_enabled: slippageEnabled,
        taker_fee_rate: Number(feeRateInput),
        slippage_min_usd: Number(slipMinInput),
        slippage_max_usd: Number(slipMaxInput)
      })
    });
  };

  const updateLatency = async () => {
    if (!evalId) return;
    await fetch(`/api/evals/${evalId}/latency`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        latency_enabled: latencyEnabled,
        latency_min_sec: Number(latencyMinInput),
        latency_max_sec: Number(latencyMaxInput)
      })
    });
  };

  const updateProfitTarget = async () => {
    if (!evalId) return;
    const value = profitTargetInput.trim();
    await fetch(`/api/evals/${evalId}/profit-target`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profit_target_pct: value ? Number(value) : null })
    });
  };

  const updateDynamicTp = async () => {
    if (!evalId) return;
    await fetch(`/api/evals/${evalId}/dynamic-tp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dynamic_tp_enabled: dynamicTpEnabled })
    });
  };

  const updateDailyDdGuard = async () => {
    if (!evalId) return;
    await fetch(`/api/evals/${evalId}/daily-dd-guard`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: dailyDdGuardEnabled,
        risk_multiple: 0,
        buffer_pct: 0,
        buffer_usd: Number(dailyDdGuardThresholdUsdInput),
        auto_resume_on_daily_reset: dailyDdGuardAutoResume,
        close_open_positions_on_trigger: dailyDdGuardCloseOpen
      })
    });
    setDailyDdGuardDirty(false);
  };

  const updateWebhookPassthrough = async () => {
    if (!evalId) return;
    const res = await fetch(`/api/evals/${evalId}/webhook-passthrough`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: webhookPassthroughEnabled,
        url: webhookPassthroughUrl.trim() || null
      })
    });
    if (!res.ok) return;
    const updated = (await res.json()) as EvalDetail;
    setDetail(updated);
    setWebhookPassthroughDirty(false);
  };

  const deleteEval = async () => {
    if (!evalId) return;
    const confirmDelete = window.confirm("Delete this eval? This cannot be undone.");
    if (!confirmDelete) return;
    await fetch(`/api/evals/${evalId}`, { method: "DELETE" });
    router.replace("/");
  };

  const detailId = detail?.id ?? "loading";
  const equityFlash = useFlashDelta(`equity-${detailId}`, detail?.current_equity ?? null);
  const avgWinBuckets = useMemo(() => {
    const buckets = [0, 0, 0, 0];
    trades.forEach((trade) => {
      if (trade.r_multiple == null || trade.r_multiple <= 0) return;
      if (trade.r_multiple < 0.5) buckets[0] += 1;
      else if (trade.r_multiple < 1) buckets[1] += 1;
      else if (trade.r_multiple < 2) buckets[2] += 1;
      else buckets[3] += 1;
    });
    return buckets;
  }, [trades]);
  const maxBucket = Math.max(1, ...avgWinBuckets);

  if (!detail) {
    return <div className="text-slate-400">Loading eval...</div>;
  }

  const dailyUsed = Math.max(
    0,
    (detail.day_start_equity - detail.current_equity) / Math.max(detail.day_start_equity, 1)
  );
  const dailyHeadroom = Math.max(
    0,
    (detail.current_equity - detail.day_start_equity) / Math.max(detail.day_start_equity, 1)
  );
  const maxUsed = Math.max(
    0,
    (detail.starting_balance - detail.current_equity) / Math.max(detail.starting_balance, 1)
  );
  const maxHeadroom = Math.max(
    0,
    (detail.current_equity - detail.starting_balance) / Math.max(detail.starting_balance, 1)
  );
  const resetAt = detail.daily_reset_at_ts ? new Date(detail.daily_reset_at_ts).getTime() : null;
  const resetSeconds = resetAt != null ? Math.max(0, Math.floor((resetAt - now) / 1000)) : null;
  const equityBaseColor =
    detail.current_equity > detail.starting_balance
      ? "text-success"
      : detail.current_equity < detail.starting_balance
        ? "text-danger"
        : "text-slate-400";
  const equityFlashClass =
    equityFlash.flash
      ? equityFlash.direction === "up"
        ? "text-success"
        : "text-danger"
      : equityBaseColor;
  const profitRemainingColor =
    detail.profit_remaining_usd == null
      ? "text-slate-400"
      : "text-neon";
  const maxFloor = detail.starting_balance * (1 - detail.max_dd_pct);
  const dailyFloor = detail.day_start_equity * (1 - detail.daily_dd_pct);
  const nextDailyFloor = detail.current_equity * (1 - detail.daily_dd_pct);
  const dailyRemainingUsd = Math.max(0, detail.current_equity - dailyFloor);
  const maxRemainingUsd = Math.max(0, detail.current_equity - maxFloor);
  const hasRolling = detail.rolling_avg_pnl_per_trade != null;
  const dailyBreach = dailyUsed >= detail.daily_dd_pct;
  const maxBreach = maxUsed >= detail.max_dd_pct;
  const profitProgress = Math.max(0, Math.min(1, detail.profit_progress_pct ?? 0));
  const dailyLimitPct = detail.daily_dd_pct
    ? Math.min(100, (dailyUsed / Math.max(detail.daily_dd_pct, 0.0001)) * 100)
    : 0;
  const maxLimitPct = detail.max_dd_pct
    ? Math.min(100, (maxUsed / Math.max(detail.max_dd_pct, 0.0001)) * 100)
    : 0;
  const ddRisk = Math.max(
    detail.daily_dd_pct ? dailyUsed / Math.max(detail.daily_dd_pct, 0.0001) : 0,
    detail.max_dd_pct ? maxUsed / Math.max(detail.max_dd_pct, 0.0001) : 0
  );
  const healthFillClass =
    ddRisk >= 1
      ? "from-danger via-danger to-neonMagenta"
      : ddRisk >= 0.7
        ? "from-warn via-neonMagenta to-neon"
        : "from-success via-neon to-neonSoft";
  const riskRemainingR =
    detail.risk_usd && detail.risk_usd > 0
      ? dailyRemainingUsd / detail.risk_usd
      : null;
  const riskRemainingClass =
    riskRemainingR == null
      ? "text-slate-400"
      : riskRemainingR > 2
        ? "text-success"
        : riskRemainingR >= 1
          ? "text-warn"
          : "text-danger";
  const isPassed = detail.status === "PASSED";
  const activePositionId = detail.open_positions?.[0]?.id ?? null;
  const ddGuardBlocking = Boolean(detail.daily_dd_guard_blocking);
  const dailyDdAllowanceUsd = Math.max(0, detail.day_start_equity * detail.daily_dd_pct);
  const guardSliderMax = Math.max(1, Math.ceil(dailyDdAllowanceUsd));
  const guardThresholdDraft = Math.max(
    0,
    Math.min(guardSliderMax, Number(dailyDdGuardThresholdUsdInput || 0))
  );

  return (
    <div className="space-y-8">
      {isPassed ? (
        <div className="rounded-xl border border-success/40 bg-success/10 px-4 py-3 text-sm text-success shadow-glowSoft animate-pass-in">
          <div className="flex items-center gap-2 font-semibold uppercase tracking-[0.2em]">
            <CheckCircle className="h-4 w-4" />
            Evaluation Passed
          </div>
        </div>
      ) : null}
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link href="/">
            <Button variant="outline">Return to Dashboard</Button>
          </Link>
          <div>
            <p className="text-xs uppercase tracking-[0.25em] text-neonSoft">{detail.strategy_key}</p>
            <h2 className="text-2xl font-semibold text-slate-100">{detail.name}</h2>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={pauseEval}>
            Pause Eval
          </Button>
          <Button variant="default" onClick={resumeEval}>
            Resume Eval
          </Button>
          <Button variant="danger" onClick={deleteEval}>
            Delete Eval
          </Button>
        </div>
      </section>

      <section
        className={`grid gap-4 md:grid-cols-3 xl:grid-cols-6 ${isPassed ? "border-t border-success/40 pt-4" : ""}`}
      >
        <StatCard title="Status" value={detail.status} hint={detail.symbol} />
        <StatCard title="Starting Balance" value={formatCurrency(detail.starting_balance)} />
        <StatCard title="Current Balance" value={formatCurrency(detail.current_balance)} />
        <StatCard
          title="Current Equity"
          value={formatCurrency(detail.current_equity)}
          valueClassName={`transition-colors duration-700 ease-out ${equityFlashClass}`}
        />
        <StatCard
          title="Daily DD Used"
          value={formatPercent(dailyUsed)}
          valueClassName={
            dailyUsed > 0
              ? `text-danger ${dailyBreach ? "animate-pulse-slow motion-reduce:animate-none" : ""}`
              : "text-slate-400"
          }
          hint={dailyHeadroom > 0 ? `+${formatPercent(dailyHeadroom)} headroom` : `Limit ${formatPercent(detail.daily_dd_pct)}`}
        />
        <StatCard
          title="Daily DD Reset In"
          value={
            resetSeconds == null
              ? "--"
              : resetSeconds > 0
                ? formatCountdown(resetSeconds)
                : "Resetting…"
          }
        />
        <StatCard
          title="DD Guard"
          value={
            !detail.daily_dd_guard_enabled
              ? "Off"
              : ddGuardBlocking
                ? "Blocking"
                : "Armed"
          }
          valueClassName={
            !detail.daily_dd_guard_enabled
              ? "text-slate-400"
              : ddGuardBlocking
                ? "text-danger"
                : "text-warn"
          }
          hint={
            detail.daily_dd_guard_enabled
              ? `Remain ${formatCurrency(detail.daily_dd_remaining_usd ?? 0)} / Threshold ${formatCurrency(detail.daily_dd_guard_threshold_usd ?? 0)}`
              : "Protect entries near daily limit"
          }
        />
        <StatCard
          title="Fixed Risk USD"
          value={detail.risk_usd != null ? formatCurrency(detail.risk_usd) : "--"}
        />
        <Card className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-neon/6 via-transparent to-accent/10" />
          <CardHeader>
            <CardTitle className="text-[10px] uppercase tracking-[0.3em] text-slate-500">
              Avg Win R
            </CardTitle>
          </CardHeader>
          <CardContent className="relative space-y-3">
            <div className="text-2xl font-semibold text-slate-100 tabular">
              {detail.avg_win_r != null
                ? `${detail.avg_win_r.toFixed(2)} (${detail.n_wins_r ?? 0})`
                : "--"}
            </div>
            {trades.length ? (
              <div className="flex items-end gap-2 text-[10px] text-slate-500">
                {avgWinBuckets.map((count, index) => (
                  <div key={index} className="flex flex-col items-center gap-1">
                    <div
                      className="w-3 rounded-full bg-neon/70"
                      style={{ height: `${Math.max(4, (count / maxBucket) * 28)}px` }}
                    />
                    <span className="tabular">
                      {index === 0 ? "0-0.5" : index === 1 ? "0.5-1" : index === 2 ? "1-2" : "2+"}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card className="md:col-span-2 xl:col-span-3">
          <CardHeader>
            <CardTitle>Daily DD Protection</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant={dailyDdGuardEnabled ? "default" : "outline"}
                onClick={() => {
                  setDailyDdGuardDirty(true);
                  setDailyDdGuardEnabled((v) => !v);
                }}
              >
                {dailyDdGuardEnabled ? "Guard ON" : "Guard OFF"}
              </Button>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={dailyDdGuardAutoResume}
                  onChange={(e) => {
                    setDailyDdGuardDirty(true);
                    setDailyDdGuardAutoResume(e.target.checked);
                  }}
                />
                Auto resume on daily reset
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={dailyDdGuardCloseOpen}
                  onChange={(e) => {
                    setDailyDdGuardDirty(true);
                    setDailyDdGuardCloseOpen(e.target.checked);
                  }}
                />
                Close open positions on trigger
              </label>
              <Button variant="outline" onClick={updateDailyDdGuard}>
                Save DD Guard
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div>
                <p className="mb-1 text-xs text-slate-500">Stop trading within this many dollars of Daily DD</p>
                <input
                  type="range"
                  min={0}
                  max={guardSliderMax}
                  step={1}
                  value={guardThresholdDraft}
                  onChange={(e) => {
                    setDailyDdGuardDirty(true);
                    setDailyDdGuardThresholdUsdInput(e.target.value);
                  }}
                  className="w-full accent-cyan-400"
                />
                <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
                  <span>$0</span>
                  <span className="font-semibold text-slate-100">
                    {formatCurrency(guardThresholdDraft)}
                  </span>
                  <span>{formatCurrency(dailyDdAllowanceUsd)}</span>
                </div>
              </div>
              <div>
                <p className="mb-1 text-xs text-slate-500">Threshold (USD)</p>
                <Input
                  value={dailyDdGuardThresholdUsdInput}
                  onChange={(e) => {
                    setDailyDdGuardDirty(true);
                    setDailyDdGuardThresholdUsdInput(e.target.value);
                  }}
                />
              </div>
              <div>
                <p className="mb-1 text-xs text-slate-500">Current remaining to Daily DD</p>
                <div className="h-10 rounded-md border border-border/60 bg-panel/70 px-3 py-2 text-sm text-slate-100">
                  {formatCurrency(detail.daily_dd_remaining_usd ?? 0)}
                </div>
              </div>
            </div>
            <div className="text-xs text-slate-400">
              Status:{" "}
              {detail.daily_dd_guard_enabled
                ? ddGuardBlocking
                  ? "Blocking new entries"
                  : "Armed"
                : "Disabled"}
              {detail.daily_dd_guard_reason ? ` | ${detail.daily_dd_guard_reason}` : ""}
            </div>
            {detail.daily_dd_guard_blocks_entries_until ? (
              <div className="text-xs text-slate-400">
                Blocks until reset: {new Date(detail.daily_dd_guard_blocks_entries_until).toLocaleString()}
              </div>
            ) : null}
          </CardContent>
        </Card>
        <StatCard
          title="Win Rate"
          value={
            detail.win_rate_r != null
              ? `${detail.win_rate_r.toFixed(1)}% (${detail.n_valid_r ?? 0})`
              : "--"
          }
        />
        <StatCard
          title="Expectancy (R)"
          value={
            detail.expectancy_r != null
              ? `${detail.expectancy_r.toFixed(2)} (${detail.n_valid_r ?? 0})`
              : "--"
          }
        />
        <StatCard
          title="Max DD Used"
          value={formatPercent(maxUsed)}
          valueClassName={
            maxUsed > 0
              ? `text-danger ${maxBreach ? "animate-pulse-slow motion-reduce:animate-none" : ""}`
              : "text-slate-400"
          }
          hint={maxHeadroom > 0 ? `+${formatPercent(maxHeadroom)} headroom` : `Limit ${formatPercent(detail.max_dd_pct)}`}
        />
      </section>

      <section className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Evaluation Health</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-slate-500">
              <span>Composite survivability</span>
              <span className={ddRisk >= 1 ? "text-danger" : ddRisk >= 0.7 ? "text-warn" : "text-success"}>
                {Math.round(profitProgress * 100)}%
              </span>
            </div>
            <div className="relative h-3 w-full rounded-full bg-panelSoft/80">
              <div
                className={`h-3 rounded-full bg-gradient-to-r ${healthFillClass} shadow-glowSoft transition-[width] duration-300`}
                style={{ width: `${profitProgress * 100}%` }}
              />
              <span
                className="absolute top-[-2px] h-[16px] w-[2px] bg-warn/80"
                style={{ left: `${dailyLimitPct}%` }}
                title="Daily DD limit usage"
              />
              <span
                className="absolute top-[-2px] h-[16px] w-[2px] bg-danger/80"
                style={{ left: `${maxLimitPct}%` }}
                title="Max DD limit usage"
              />
            </div>
            {riskRemainingR != null ? (
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-slate-500">
                <span>Risk Remaining Today</span>
                <span className={`tabular ${riskRemainingClass}`}>{riskRemainingR.toFixed(1)} R</span>
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Risk & Targets</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5 text-sm">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-slate-500">
                <span>Daily DD Used</span>
                <span className={dailyUsed > 0.5 ? "text-danger" : "text-neonSoft"}>
                  {formatPercent(dailyUsed)}
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-panelSoft/80">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-neon to-accent shadow-glowSoft transition-[width] duration-300"
                  style={{ width: `${Math.min(100, dailyUsed * 100)}%` }}
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-slate-500">
                <span>Max DD Used</span>
                <span className={maxUsed > 0.5 ? "text-danger" : "text-neonSoft"}>
                  {formatPercent(maxUsed)}
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-panelSoft/80">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-neonMagenta to-accent shadow-glowMagenta transition-[width] duration-300"
                  style={{ width: `${Math.min(100, maxUsed * 100)}%` }}
                />
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-slate-500">
                <span>Profit Target</span>
                <span className="text-neonSoft">
                  {detail.profit_progress_pct != null
                    ? `${(detail.profit_progress_pct * 100).toFixed(1)}%`
                    : "--"}
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-panelSoft/80">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-success to-neon shadow-glowSoft transition-[width] duration-300"
                  style={{ width: `${Math.min(100, (detail.profit_progress_pct ?? 0) * 100)}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Equity & Drawdown</CardTitle>
          </CardHeader>
          <CardContent>
            <EquityDrawdownChart series={equitySeries} />
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Performance</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Wins / Losses / BE</span>
              <span className="tabular">
                {detail.wins ?? 0} / {detail.losses ?? 0} / {detail.breakeven ?? 0}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Win Rate</span>
              <span className="tabular">{detail.win_rate_pct != null ? `${detail.win_rate_pct.toFixed(1)}%` : "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Profit Factor</span>
              <span className="tabular">{detail.profit_factor != null ? detail.profit_factor.toFixed(2) : "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Avg Win</span>
              <span className="tabular">{detail.avg_win != null ? formatCurrency(detail.avg_win) : "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Avg Loss</span>
              <span className="tabular">{detail.avg_loss != null ? formatCurrency(detail.avg_loss) : "--"}</span>
            </div>
            <div className="pt-2 text-xs text-slate-500">
              Rolling 20 trades: {hasRolling ? "ready" : "Not enough data"}
            </div>
            {hasRolling ? (
              <div className="pt-2 space-y-2 text-xs text-slate-500">
                <div className="flex justify-between">
                  <span>Rolling net P/L</span>
                  <span
                    className={`tabular ${
                      detail.rolling_net_pnl == null
                        ? "text-slate-400"
                        : detail.rolling_net_pnl > 0
                          ? "text-success"
                          : detail.rolling_net_pnl < 0
                            ? "text-danger"
                            : "text-slate-400"
                    }`}
                  >
                    {detail.rolling_net_pnl != null ? formatCurrency(detail.rolling_net_pnl) : "--"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Rolling avg P/L</span>
                  <span
                    className={`tabular ${
                      detail.rolling_avg_pnl_per_trade == null
                        ? "text-slate-400"
                        : detail.rolling_avg_pnl_per_trade > 0
                          ? "text-success"
                          : detail.rolling_avg_pnl_per_trade < 0
                            ? "text-danger"
                            : "text-slate-400"
                    }`}
                  >
                    {detail.rolling_avg_pnl_per_trade != null
                      ? formatCurrency(detail.rolling_avg_pnl_per_trade)
                      : "--"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Rolling win %</span>
                  <span className="tabular">
                    {detail.rolling_win_rate != null ? `${detail.rolling_win_rate.toFixed(1)}%` : "--"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Rolling PF</span>
                  <span className="tabular">
                    {detail.rolling_profit_factor != null ? detail.rolling_profit_factor.toFixed(2) : "--"}
                  </span>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Passing</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="grid gap-3 md:grid-cols-3">
              <div>
                <div className="text-slate-500">Profit target %</div>
                <Input value={profitTargetInput} onChange={(event) => setProfitTargetInput(event.target.value)} />
              </div>
              <div>
                <div className="text-slate-500">Target equity</div>
                <div className="tabular mt-2">
                  {detail.profit_target_equity ? formatCurrency(detail.profit_target_equity) : "--"}
                </div>
              </div>
              <div>
                <div className="text-slate-500">Remaining</div>
                <div className={`tabular mt-2 ${profitRemainingColor}`}>
                  {detail.profit_remaining_usd != null ? formatCurrency(detail.profit_remaining_usd) : "--"}
                </div>
              </div>
            </div>
            <Button variant="outline" onClick={updateProfitTarget}>
              Save Profit Target
            </Button>
            <div className="space-y-2">
              <div className="h-2 w-full rounded-full bg-panelSoft/80">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-neon to-success shadow-glowSoft transition-[width] duration-300"
                  style={{ width: `${Math.round((detail.profit_progress_pct ?? 0) * 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-xs text-slate-500">
                <span>Progress</span>
                <span>
                  {detail.profit_progress_pct != null ? `${(detail.profit_progress_pct * 100).toFixed(1)}%` : "--"}
                </span>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2 text-xs text-slate-500">
              <div>
                ETA pass (trades):{" "}
                {detail.expected_trades_to_pass != null ? detail.expected_trades_to_pass.toFixed(1) : "—"}
              </div>
              <div>
                ETA pass (days):{" "}
                {detail.expected_days_to_pass != null ? detail.expected_days_to_pass.toFixed(1) : "—"}
              </div>
            </div>
            {detail.profit_target_pct == null ? (
              <div className="text-xs text-slate-500">No profit target set.</div>
            ) : detail.expected_trades_to_pass == null ? (
              <div className="text-xs text-slate-500">Not trending to pass (insufficient rolling edge).</div>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Risk of Fail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Daily DD Remaining</span>
              <span className="tabular">{formatCurrency(dailyRemainingUsd)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Max DD Remaining</span>
              <span className="tabular">{formatCurrency(maxRemainingUsd)}</span>
            </div>
            <div className="flex justify-between text-xs text-slate-500">
              <span>ETA daily fail (trades)</span>
              <span>{detail.expected_trades_to_daily_fail != null ? detail.expected_trades_to_daily_fail.toFixed(1) : "—"}</span>
            </div>
            <div className="flex justify-between text-xs text-slate-500">
              <span>ETA max fail (trades)</span>
              <span>{detail.expected_trades_to_max_fail != null ? detail.expected_trades_to_max_fail.toFixed(1) : "—"}</span>
            </div>
            {detail.expected_trades_to_daily_fail == null && detail.expected_trades_to_max_fail == null ? (
              <div className="text-xs text-slate-500">Low fail risk (insufficient loss data).</div>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Open Positions</CardTitle>
            <Badge variant={detail.dynamic_tp_enabled ? "info" : "default"}>
              {detail.dynamic_tp_enabled ? "TP: Webhook-controlled" : "TP: Normal"}
            </Badge>
          </CardHeader>
          <CardContent>
            {detail.open_positions && detail.open_positions.length ? (
              <>
                <div className="space-y-3 md:hidden">
                  {detail.open_positions.map((position) => {
                    const risk = Math.abs(position.entry_price - position.stop_price);
                    const targetR =
                      position.tp_price != null && risk > 0
                        ? position.side === "LONG"
                          ? (position.tp_price - position.entry_price) / risk
                          : (position.entry_price - position.tp_price) / risk
                        : null;
                    return (
                      <div
                        key={position.id}
                        className={`rounded-lg border border-border/70 bg-panel/70 p-3 ${
                          activePositionId === position.id
                            ? position.side === "LONG"
                              ? "halo-long"
                              : "halo-short"
                            : ""
                        }`}
                        onClick={() => {
                          setActivePosition(position);
                          setPositionDialogOpen(true);
                        }}
                      >
                        <div className="flex items-center justify-between">
                          <Badge variant={position.side === "LONG" ? "success" : "danger"}>
                            {position.side}
                          </Badge>
                          <span className="tabular text-slate-400">{position.qty.toFixed(4)}</span>
                        </div>
                        <div className="mt-3 grid grid-cols-1 gap-3 text-sm text-slate-500 sm:grid-cols-2">
                          <div>
                            <div>Entry</div>
                            <div className="tabular text-slate-200 break-words">
                              {formatCurrency(position.entry_price)}
                            </div>
                          </div>
                          <div>
                            <div>Stop</div>
                            <div className="tabular text-slate-200 break-words">
                              {formatCurrency(position.stop_price)}
                            </div>
                          </div>
                          <div>
                            <div>Target</div>
                            {position.tp_price == null ? (
                              <Badge variant="magenta">Dynamic</Badge>
                            ) : (
                              <div className="tabular text-neonSoft break-words">
                                {targetR?.toFixed(2) ?? "--"}
                              </div>
                            )}
                          </div>
                          <div>
                            <div>Open P/L</div>
                            <div className="tabular text-slate-200 break-words">
                              {detail.last_price != null
                                ? formatCurrency(
                                    position.side === "LONG"
                                      ? (detail.last_price - (position.entry_fill_price ?? position.entry_price)) *
                                          position.qty
                                      : ((position.entry_fill_price ?? position.entry_price) - detail.last_price) *
                                          position.qty
                                  )
                                : "--"}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="hidden md:block overflow-x-auto">
                  <table className="w-full min-w-[770px] table-fixed text-sm tabular">
                  <colgroup>
                    <col className="w-[90px]" />
                    <col className="w-[120px]" />
                    <col className="w-[140px]" />
                    <col className="w-[140px]" />
                    <col className="w-[140px]" />
                    <col className="w-[140px]" />
                  </colgroup>
                  <thead className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    <tr>
                      <th className="px-3 py-2 text-left">Side</th>
                      <th className="px-3 py-2 text-right">Qty</th>
                      <th className="px-3 py-2 text-right">Entry</th>
                      <th className="px-3 py-2 text-right">Stop</th>
                      <th className="px-3 py-2 text-right">Target R</th>
                      <th className="px-3 py-2 text-right">Open P/L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.open_positions.map((position) => {
                      return (
                        <OpenPositionRow
                          key={position.id}
                          position={position}
                          lastPrice={detail.last_price ?? null}
                          isActive={activePositionId === position.id}
                          onSelect={(selected) => {
                            setActivePosition(selected);
                            setPositionDialogOpen(true);
                          }}
                        />
                      );
                    })}
                  </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="text-sm text-slate-500">No open positions</div>
            )}
          </CardContent>
        </Card>
        <Dialog
          open={positionDialogOpen}
          onOpenChange={(open) => {
            setPositionDialogOpen(open);
            if (!open) {
              setActivePosition(null);
            }
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Position Details</DialogTitle>
            </DialogHeader>
            {activePosition ? (
              <div className="grid gap-3 text-sm">
                {(() => {
                  const risk = Math.abs(activePosition.entry_price - activePosition.stop_price);
                  const targetR =
                    activePosition.tp_price != null && risk > 0
                      ? activePosition.side === "LONG"
                        ? (activePosition.tp_price - activePosition.entry_price) / risk
                        : (activePosition.entry_price - activePosition.tp_price) / risk
                      : null;
                  return (
                    <>
                <div className="flex justify-between">
                  <span className="text-slate-500">Side</span>
                  <span>{activePosition.side}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Qty</span>
                  <span className="tabular-nums">{activePosition.qty.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Entry Price</span>
                  <span className="tabular-nums">{formatCurrency(activePosition.entry_price)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Entry Fill</span>
                  <span className="tabular-nums">
                    {activePosition.entry_fill_price ? formatCurrency(activePosition.entry_fill_price) : "--"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Stop</span>
                  <span className="tabular-nums">{formatCurrency(activePosition.stop_price)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Target R</span>
                  <span
                    className={`tabular-nums ${
                      activePosition.tp_price == null ? "text-neonMagenta" : "text-neonSoft"
                    }`}
                  >
                    {activePosition.tp_price == null
                      ? "Dynamic"
                      : targetR != null
                        ? targetR.toFixed(2)
                        : "--"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Entry Fee</span>
                  <span className="tabular-nums">
                    {activePosition.entry_fee != null ? formatCurrency(activePosition.entry_fee) : "--"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Entry Slippage</span>
                  <span className="tabular-nums">
                    {activePosition.entry_slippage != null ? formatCurrency(activePosition.entry_slippage) : "--"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Opened</span>
                  <span>{activePosition.opened_at}</span>
                </div>
                    </>
                  );
                })()}
              </div>
            ) : null}
          </DialogContent>
        </Dialog>

        <Card>
          <CardHeader>
            <CardTitle>Recent Events</CardTitle>
          </CardHeader>
          <CardContent>
            <EventList events={events} />
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Risk & Costs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <div className="text-slate-500">Fixed Risk USD</div>
                <div className="flex gap-2">
                  <Input value={riskInput} onChange={(event) => setRiskInput(event.target.value)} />
                  <Button variant="outline" onClick={updateRisk}>
                    Update
                  </Button>
                </div>
              </div>
              <div>
                <div className="text-slate-500">Fees + Slippage</div>
                <div className="flex gap-2">
                  <Button variant={feeEnabled ? "default" : "outline"} onClick={() => setFeeEnabled(!feeEnabled)}>
                    Fees {feeEnabled ? "ON" : "OFF"}
                  </Button>
                  <Button
                    variant={slippageEnabled ? "default" : "outline"}
                    onClick={() => setSlippageEnabled(!slippageEnabled)}
                  >
                    Slippage {slippageEnabled ? "ON" : "OFF"}
                  </Button>
                </div>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div>
                <div className="text-xs text-slate-500 mb-1">Taker fee rate</div>
                <Input value={feeRateInput} onChange={(event) => setFeeRateInput(event.target.value)} />
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">Slippage min (USD)</div>
                <Input value={slipMinInput} onChange={(event) => setSlipMinInput(event.target.value)} />
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-1">Slippage max (USD)</div>
                <Input value={slipMaxInput} onChange={(event) => setSlipMaxInput(event.target.value)} />
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <div className="text-slate-500">Order Latency</div>
                <div className="flex gap-2">
                  <Button
                    variant={latencyEnabled ? "default" : "outline"}
                    onClick={() => setLatencyEnabled(!latencyEnabled)}
                  >
                    Latency {latencyEnabled ? "ON" : "OFF"}
                  </Button>
                  <Button variant="outline" onClick={updateLatency}>
                    Save Latency
                  </Button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-slate-500 mb-1">Min sec</div>
                  <Input value={latencyMinInput} onChange={(event) => setLatencyMinInput(event.target.value)} />
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">Max sec</div>
                  <Input value={latencyMaxInput} onChange={(event) => setLatencyMaxInput(event.target.value)} />
                </div>
              </div>
            </div>
            <div className="rounded-lg border border-border/70 bg-panelSoft/60 p-3">
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-neon"
                  checked={dynamicTpEnabled}
                  onChange={(event) => setDynamicTpEnabled(event.target.checked)}
                />
                <div>
                  <div className="font-medium">Dynamic TP (webhook exits)</div>
                  <div className="text-xs text-slate-500">
                    When enabled, TP in entry webhooks is ignored. Positions exit only via exit webhook.
                  </div>
                </div>
              </label>
              <div className="mt-3">
                <Button variant="outline" onClick={updateDynamicTp}>
                  Save TP Mode
                </Button>
              </div>
            </div>
            <div className="rounded-lg border border-border/70 bg-panelSoft/60 p-3">
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-neon"
                  checked={webhookPassthroughEnabled}
                  onChange={(event) => {
                    setWebhookPassthroughEnabled(event.target.checked);
                    setWebhookPassthroughDirty(true);
                  }}
                />
                <div>
                  <div className="font-medium">Strategy Webhook Passthrough</div>
                  <div className="text-xs text-slate-500">
                    This setting is stored on the linked strategy and shared by every eval using it.
                  </div>
                </div>
              </label>
              <div className="mt-3">
                <div className="text-xs text-slate-500 mb-1">Passthrough URL (full URL)</div>
                <Input
                  value={webhookPassthroughUrl}
                  onChange={(event) => {
                    setWebhookPassthroughUrl(event.target.value);
                    setWebhookPassthroughDirty(true);
                  }}
                  placeholder="http://10.0.0.15:9000/hooks/tradingview"
                />
              </div>
              <div className="mt-3 rounded-md border border-border/60 bg-panel/70 px-3 py-2 text-xs">
                <div className="text-slate-500">Current saved passthrough</div>
                <div className="mt-1 text-slate-200">
                  {detail.webhook_passthrough_enabled
                    ? detail.webhook_passthrough_url || "(enabled, URL not set)"
                    : "Disabled"}
                </div>
                {webhookPassthroughDirty ? (
                  <div className="mt-1 text-warn">Unsaved changes</div>
                ) : null}
              </div>
              <div className="mt-3">
                <Button variant="outline" onClick={updateWebhookPassthrough}>
                  Save Passthrough
                </Button>
              </div>
            </div>
            <Button variant="outline" onClick={updateCosts}>
              Save Cost Settings
            </Button>
            <div className="grid gap-3 md:grid-cols-2 text-xs text-slate-500">
              <div title="Taker fee applied on entry and exit fills.">
                Fees paid: {detail.total_fees_paid != null ? formatCurrency(detail.total_fees_paid) : "--"}
              </div>
              <div>
                <span title="Uniform random slippage applied against the trader on entry and exit fills.">
                  Slippage impact:
                </span>{" "}
                {detail.total_slippage_impact != null ? formatCurrency(detail.total_slippage_impact) : "--"}
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Drawdown Watermarks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Max DD Floor</span>
              <span className="tabular">{formatCurrency(maxFloor)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Daily DD Floor</span>
              <span className="tabular">{formatCurrency(dailyFloor)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Next Daily Floor</span>
              <span className="tabular">{formatCurrency(nextDailyFloor)}</span>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Webhook Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div>
              <div className="text-slate-500">Webhook URL</div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="break-all text-slate-100">
                  {typeof window !== "undefined"
                    ? `${window.location.origin}/api/webhook/${detail.strategy_key}`
                    : ""}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    navigator.clipboard.writeText(
                      `${window.location.origin}/api/webhook/${detail.strategy_key}`
                    )
                  }
                >
                  Copy
                </Button>
              </div>
            </div>
            <div className="flex gap-6">
              <div>
                <div className="text-slate-500">Strategy</div>
                <div className="text-slate-100">{detail.strategy_name || detail.strategy_key}</div>
                <div className="text-xs text-slate-500">{detail.strategy_key}</div>
              </div>
              <div>
                <div className="text-slate-500">Symbol</div>
                <div className="text-slate-100">{detail.symbol}</div>
              </div>
            </div>
            <div>
              <div className="text-slate-500">Passthrough URL</div>
              <div className="text-slate-100 break-all">
                {detail.webhook_passthrough_enabled
                  ? detail.webhook_passthrough_url || "(enabled, URL not set)"
                  : "Disabled"}
              </div>
            </div>
            <div>
              <div className="text-slate-500">TradingView JSON</div>
              <div className="mt-2 rounded-lg border border-border/80 bg-panelSoft/60 p-3 text-xs text-slate-300">
                {`{\"ticker\":\"${detail.symbol}USDT\",\"side\":\"LONG\",\"entry\":null,\"stop\":93400,\"tp\":94800}`}
              </div>
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() =>
                  navigator.clipboard.writeText(
                    `{\"ticker\":\"${detail.symbol}USDT\",\"side\":\"LONG\",\"entry\":null,\"stop\":93400,\"tp\":94800}`
                  )
                }
              >
                Copy JSON
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <Card>
          <CardHeader>
            <CardTitle>Trade History</CardTitle>
          </CardHeader>
          <CardContent>
            <TradeTable trades={trades} />
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
