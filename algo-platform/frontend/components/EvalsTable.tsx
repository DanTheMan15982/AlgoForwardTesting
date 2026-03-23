"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCountdown, formatCurrency, formatPercent } from "@/lib/format";
import { useRealtimeStore, EvalSummary } from "@/lib/store";
import { useEffect, useState } from "react";
import { useFlashDelta } from "@/lib/useFlashDelta";

function statusVariant(status: string) {
  if (status === "ACTIVE") return "success";
  if (status === "FAILED") return "danger";
  if (status === "PAUSED") return "warning";
  if (status === "PASSED") return "info";
  return "default";
}

type EvalsTableProps = {
  evals: EvalSummary[];
};

export function EvalsTable({ evals }: EvalsTableProps) {
  const prices = useRealtimeStore((s) => s.prices);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <Table className="tabular min-w-[980px]">
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Symbol</TableHead>
          <TableHead>Strategy</TableHead>
          <TableHead className="text-right">Equity</TableHead>
          <TableHead className="text-center">W-L</TableHead>
          <TableHead className="text-right">Win%</TableHead>
          <TableHead className="text-right">PF</TableHead>
          <TableHead className="text-right">Profit Rem</TableHead>
          <TableHead className="text-right">ETA Pass</TableHead>
          <TableHead className="text-right">ETA Fail (D)</TableHead>
          <TableHead className="text-right">ETA Fail (M)</TableHead>
          <TableHead className="text-right">Daily DD</TableHead>
          <TableHead className="text-right">Reset In</TableHead>
          <TableHead className="text-right">Max DD</TableHead>
          <TableHead className="text-right">Last Price</TableHead>
          <TableHead className="text-right">Open P/L</TableHead>
          <TableHead>Open</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {evals.map((evalRow) => (
          <EvalTableRow key={evalRow.id} evalRow={evalRow} price={prices[evalRow.symbol]?.price ?? null} now={now} />
        ))}
      </TableBody>
    </Table>
  );
}

type EvalRowProps = {
  evalRow: EvalSummary;
  price: number | null;
  now: number;
};

function EvalTableRow({ evalRow, price, now }: EvalRowProps) {
  const router = useRouter();
  const dailyUsed = Math.max(
    0,
    (evalRow.day_start_equity - evalRow.current_equity) / Math.max(evalRow.day_start_equity, 1)
  );
  const dailyHeadroom = Math.max(
    0,
    (evalRow.current_equity - evalRow.day_start_equity) / Math.max(evalRow.day_start_equity, 1)
  );
  const maxUsed = Math.max(
    0,
    (evalRow.starting_balance - evalRow.current_equity) / Math.max(evalRow.starting_balance, 1)
  );
  const maxHeadroom = Math.max(
    0,
    (evalRow.current_equity - evalRow.starting_balance) / Math.max(evalRow.starting_balance, 1)
  );
  const resolvedPrice = price ?? evalRow.last_price ?? null;
  const resetAt = evalRow.daily_reset_at_ts ? new Date(evalRow.daily_reset_at_ts).getTime() : null;
  const secondsRemaining = resetAt != null ? Math.max(0, Math.floor((resetAt - now) / 1000)) : null;
  const wins = evalRow.wins != null ? Number(evalRow.wins) : null;
  const losses = evalRow.losses != null ? Number(evalRow.losses) : null;
  const wl = wins != null && losses != null ? `${wins}-${losses}` : "—";
  const winRate = evalRow.win_rate_pct != null ? `${evalRow.win_rate_pct.toFixed(1)}%` : "--";
  const profitFactor = evalRow.profit_factor != null ? evalRow.profit_factor.toFixed(2) : "--";
  const profitRemainingValue = evalRow.profit_remaining_usd;
  const profitRemaining =
    profitRemainingValue != null ? formatCurrency(profitRemainingValue) : "--";
  const etaPass = evalRow.expected_days_to_pass != null ? `${evalRow.expected_days_to_pass.toFixed(1)}d` : "--";
  const etaDailyFail =
    evalRow.expected_trades_to_daily_fail != null ? `${evalRow.expected_trades_to_daily_fail.toFixed(1)}t` : "--";
  const etaMaxFail =
    evalRow.expected_trades_to_max_fail != null ? `${evalRow.expected_trades_to_max_fail.toFixed(1)}t` : "--";
  const computedOpenPnl =
    evalRow.open_position && resolvedPrice != null
      ? (evalRow.open_position.side === "LONG"
          ? (resolvedPrice - evalRow.open_position.entry_price)
          : (evalRow.open_position.entry_price - resolvedPrice)) * evalRow.open_position.qty
      : evalRow.open_pnl ?? null;
  const openPnlFlash = useFlashDelta(`openpnl-${evalRow.id}`, computedOpenPnl ?? null, 350);
  const equityFlash = useFlashDelta(`equity-${evalRow.id}`, evalRow.current_equity, 350);
  const openPnlColor =
    computedOpenPnl == null
      ? "text-slate-400"
      : computedOpenPnl > 0
        ? "text-success"
        : computedOpenPnl < 0
          ? "text-danger"
          : "text-slate-400";
  const equityColor =
    evalRow.current_equity > evalRow.starting_balance
      ? "text-success"
      : evalRow.current_equity < evalRow.starting_balance
        ? "text-danger"
        : "text-slate-400";
  const equityFlashClass =
    equityFlash.flash && equityFlash.direction === "up"
      ? "text-success"
      : equityFlash.flash && equityFlash.direction === "down"
        ? "text-danger"
        : equityColor;
  const profitRemainingColor =
    profitRemainingValue == null ? "text-slate-400" : "text-neon";

  return (
    <TableRow
      className="cursor-pointer"
      onClick={() => router.push(`/evals/${evalRow.id}`)}
    >
      <TableCell className="font-medium">
        <Link
          href={`/evals/${evalRow.id}`}
          className="text-slate-100 hover:text-neon"
        >
          {evalRow.name}
        </Link>
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={statusVariant(evalRow.status)}>{evalRow.status}</Badge>
          <Badge variant={evalRow.dynamic_tp_enabled ? "info" : "default"}>
            {evalRow.dynamic_tp_enabled ? "TP: Webhook" : "TP: Normal"}
          </Badge>
        </div>
      </TableCell>
      <TableCell>{evalRow.symbol}</TableCell>
      <TableCell>{evalRow.strategy_key}</TableCell>
      <TableCell className={`tabular-nums min-w-[110px] text-right transition-colors duration-700 ease-out ${equityFlashClass}`}>
        {formatCurrency(evalRow.current_equity)}
      </TableCell>
      <TableCell className="tabular-nums whitespace-nowrap text-center">{wl}</TableCell>
      <TableCell className="tabular-nums text-right">{winRate}</TableCell>
      <TableCell className="tabular-nums text-right">{profitFactor}</TableCell>
      <TableCell className={`tabular-nums min-w-[120px] text-right ${profitRemainingColor}`}>
        {profitRemaining}
      </TableCell>
      <TableCell className="tabular-nums text-right">{etaPass}</TableCell>
      <TableCell className="tabular-nums text-right">{etaDailyFail}</TableCell>
      <TableCell className="tabular-nums text-right">{etaMaxFail}</TableCell>
      <TableCell
        className={`text-right ${
          dailyUsed > 0 ? "text-danger" : "text-slate-400"
        }`}
      >
        <div className="tabular-nums">{formatPercent(dailyUsed)}</div>
        {dailyHeadroom > 0 ? (
          <div className="text-xs text-slate-500">+{formatPercent(dailyHeadroom)} headroom</div>
        ) : null}
      </TableCell>
      <TableCell className="text-slate-500 text-right tabular-nums min-w-[90px]">
        {secondsRemaining != null
          ? secondsRemaining > 0
            ? formatCountdown(secondsRemaining)
            : "Resetting…"
          : "--"}
      </TableCell>
      <TableCell
        className={`tabular-nums text-right ${
          maxUsed > 0 ? "text-danger" : "text-slate-400"
        }`}
      >
        <div className="tabular-nums">{formatPercent(maxUsed)}</div>
        {maxHeadroom > 0 ? (
          <div className="text-xs text-slate-500">+{formatPercent(maxHeadroom)} headroom</div>
        ) : null}
      </TableCell>
      <TableCell className="tabular-nums min-w-[120px] text-right">
        {resolvedPrice != null ? formatCurrency(resolvedPrice) : "--"}
      </TableCell>
      <TableCell
        className={`tabular-nums min-w-[120px] text-right transition-colors duration-700 ease-out ${
          openPnlFlash.flash
            ? openPnlFlash.direction === "up"
              ? "text-success"
              : "text-danger"
            : openPnlColor
        }`}
      >
        {computedOpenPnl != null ? formatCurrency(computedOpenPnl) : "--"}
      </TableCell>
      <TableCell className={evalRow.has_open_position ? "text-success" : "text-slate-500"}>
        {evalRow.has_open_position ? "●" : "—"}
      </TableCell>
    </TableRow>
  );
}
