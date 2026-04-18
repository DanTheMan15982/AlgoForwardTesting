"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatTime } from "@/lib/format";
import { useFlashDelta } from "@/lib/useFlashDelta";

type PriceCardProps = {
  symbol: string;
  price?: number | null;
  ts?: string | null;
  subtitle?: string;
};

export function PriceCard({ symbol, price, ts, subtitle }: PriceCardProps) {
  const { direction, flash } = useFlashDelta(`price-${symbol}`, price ?? null, 350);
  const flashClass =
    flash && direction === "up"
      ? "text-success"
      : flash && direction === "down"
        ? "text-danger"
        : "text-slate-100";
  return (
    <Card className="relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-neon/10 via-transparent to-neonMagenta/10" />
      <CardHeader className="relative pb-3">
        <CardTitle className="text-lg tracking-[0.2em] text-slate-100">{symbol}</CardTitle>
        {subtitle ? (
          <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">{subtitle}</div>
        ) : null}
      </CardHeader>
      <CardContent className="relative flex items-end justify-between pt-3 pb-5">
        <div>
          <div
            className={`text-2xl font-semibold tabular transition-colors duration-700 ease-out ${flashClass}`}
          >
            {price != null ? formatCurrency(price) : "--"}
          </div>
          <div className="text-xs text-slate-500">
            {ts ? `Updated ${formatTime(ts)}` : "Waiting for price"}
          </div>
        </div>
        <div className="text-[10px] uppercase tracking-[0.4em] text-neon">Live</div>
      </CardContent>
    </Card>
  );
}
