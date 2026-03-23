"use client";

import { useMemo, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatCurrency, formatDateTime } from "@/lib/format";

export type TradeRow = {
  id: string;
  opened_at: string;
  closed_at?: string | null;
  side: string;
  entry_price: number;
  exit_price?: number | null;
  pnl?: number | null;
  reason?: string | null;
  r_multiple?: number | null;
  tp_disabled?: boolean | null;
  total_fees?: number | null;
  entry_slippage?: number | null;
  exit_slippage?: number | null;
  qty?: number | null;
};

type SortKey = "opened_at" | "pnl";

type TradeTableProps = {
  trades: TradeRow[];
};

export function TradeTable({ trades }: TradeTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("opened_at");

  const sortedTrades = useMemo(() => {
    return [...trades].sort((a, b) => {
      if (sortKey === "pnl") {
        return (b.pnl ?? 0) - (a.pnl ?? 0);
      }
      return new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime();
    });
  }, [trades, sortKey]);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2 text-xs text-slate-500">
        <button
          className={
            sortKey === "opened_at"
              ? "text-neon"
              : "hover:text-white"
          }
          onClick={() => setSortKey("opened_at")}
        >
          Sort by date
        </button>
        <span>•</span>
        <button
          className={
            sortKey === "pnl" ? "text-neon" : "hover:text-white"
          }
          onClick={() => setSortKey("pnl")}
        >
          Sort by P/L
        </button>
      </div>
      <div className="space-y-3 md:hidden">
        {sortedTrades.map((trade) => {
          const hasR = trade.r_multiple != null;
          const showDynamic = trade.tp_disabled === true && (trade.r_multiple ?? 0) <= 0;
          const rValue = trade.r_multiple ?? null;
          const rDisplay =
            hasR && !showDynamic
              ? `${rValue != null && rValue >= 0 ? "+" : ""}${rValue?.toFixed(2)}R`
              : "--";
          const rClass =
            rValue == null
              ? "text-slate-500"
              : rValue > 0
                ? "text-success"
                : rValue < 0
                  ? "text-danger"
                  : "text-slate-400";
          const pnlClass =
            trade.pnl == null
              ? "text-slate-500"
              : trade.pnl > 0
                ? "text-success"
                : trade.pnl < 0
                  ? "text-danger"
                  : "text-slate-400";
          return (
            <div key={trade.id} className="rounded-lg border border-border/70 bg-panel/70 p-3">
              <div className="flex items-center justify-between">
                <Badge variant={trade.side === "LONG" ? "success" : "danger"}>{trade.side}</Badge>
                <span className={`tabular text-base font-semibold ${pnlClass}`}>
                  {trade.pnl != null ? formatCurrency(trade.pnl) : "--"}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-500">
                <div>
                  <div>Opened</div>
                  <div className="text-slate-200">{formatDateTime(trade.opened_at)}</div>
                </div>
                <div>
                  <div>Closed</div>
                  <div className="text-slate-200">
                    {trade.closed_at ? formatDateTime(trade.closed_at) : "--"}
                  </div>
                </div>
                <div>
                  <div>Entry</div>
                  <div className="tabular text-slate-200">{formatCurrency(trade.entry_price)}</div>
                </div>
                <div>
                  <div>Exit</div>
                  <div className="tabular text-slate-200">
                    {trade.exit_price ? formatCurrency(trade.exit_price) : "--"}
                  </div>
                </div>
                <div>
                  <div>Reason</div>
                  <div className="text-slate-200">{trade.reason ?? "--"}</div>
                </div>
                <div>
                  <div>R</div>
                  <div className={`tabular font-semibold ${rClass}`}>{rDisplay}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="hidden md:block">
        <Table className="tabular">
          <TableHeader>
            <TableRow>
              <TableHead>Opened</TableHead>
              <TableHead>Closed</TableHead>
              <TableHead>Side</TableHead>
              <TableHead>Entry</TableHead>
              <TableHead>Exit</TableHead>
              <TableHead>P/L</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>R</TableHead>
              <TableHead>Fees</TableHead>
              <TableHead>Slippage</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedTrades.map((trade) => {
              const hasR = trade.r_multiple != null;
              const showDynamic = trade.tp_disabled === true && (trade.r_multiple ?? 0) <= 0;
              const rValue = trade.r_multiple ?? null;
              const rDisplay =
                hasR && !showDynamic
                  ? `${rValue != null && rValue >= 0 ? "+" : ""}${rValue?.toFixed(2)}R`
                  : "--";
              const rClass =
                rValue == null
                  ? "text-slate-500"
                  : rValue > 0
                    ? "text-success"
                    : rValue < 0
                      ? "text-danger"
                      : "text-slate-400";
              return (
              <TableRow key={trade.id}>
                <TableCell>{formatDateTime(trade.opened_at)}</TableCell>
                <TableCell>{trade.closed_at ? formatDateTime(trade.closed_at) : "--"}</TableCell>
                <TableCell>
                  <Badge variant={trade.side === "LONG" ? "success" : "danger"}>{trade.side}</Badge>
                </TableCell>
                <TableCell className="tabular-nums">{formatCurrency(trade.entry_price)}</TableCell>
                <TableCell className="tabular-nums">{trade.exit_price ? formatCurrency(trade.exit_price) : "--"}</TableCell>
                <TableCell
                  className={`tabular-nums font-semibold ${
                    trade.pnl == null
                      ? "text-slate-500"
                      : trade.pnl > 0
                        ? "text-success"
                        : trade.pnl < 0
                          ? "text-danger"
                          : "text-slate-400"
                  }`}
                >
                  {trade.pnl != null ? formatCurrency(trade.pnl) : "--"}
                </TableCell>
                <TableCell>{trade.reason ?? "--"}</TableCell>
                <TableCell className={`tabular-nums font-semibold ${rClass}`}>{rDisplay}</TableCell>
                <TableCell className="tabular-nums">{trade.total_fees != null ? formatCurrency(trade.total_fees) : "--"}</TableCell>
                <TableCell className="tabular-nums">
                  {trade.entry_slippage != null && trade.exit_slippage != null && trade.qty
                    ? formatCurrency((trade.entry_slippage + trade.exit_slippage) * trade.qty)
                    : "--"}
                </TableCell>
              </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
