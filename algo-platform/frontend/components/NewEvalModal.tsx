"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useRealtimeStore } from "@/lib/store";

const defaultPayload = {
  max_dd_pct: 6,
  daily_dd_pct: 3
};

export function NewEvalModal() {
  const upsertEval = useRealtimeStore((s) => s.upsertEval);
  const [open, setOpen] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    strategy_key: "",
    symbol: "BTC",
    starting_balance: "10000",
    risk_usd: "50",
    max_dd_pct: "6",
    daily_dd_pct: "3",
    fees_enabled: true,
    slippage_enabled: true,
    taker_fee_rate: "0.0004",
    slippage_min_usd: "2",
    slippage_max_usd: "20",
    profit_target_pct: "",
    latency_enabled: true,
    latency_min_sec: "2",
    latency_max_sec: "10",
    dynamic_tp_enabled: false,
    webhook_passthrough_enabled: false,
    webhook_passthrough_url: ""
  });

  const normalizePercent = (value: string, fallback: number) => {
    const parsed = Number(value);
    if (Number.isNaN(parsed)) return fallback / 100;
    return parsed > 1 ? parsed / 100 : parsed;
  };

  const handleSubmit = async () => {
    const payload = {
      name: form.name,
      strategy_key: form.strategy_key,
      symbol: form.symbol,
      starting_balance: Number(form.starting_balance),
      risk_usd: Number(form.risk_usd),
      max_dd_pct: normalizePercent(form.max_dd_pct || `${defaultPayload.max_dd_pct}`, defaultPayload.max_dd_pct),
      daily_dd_pct: normalizePercent(form.daily_dd_pct || `${defaultPayload.daily_dd_pct}`, defaultPayload.daily_dd_pct),
      fees_enabled: form.fees_enabled,
      slippage_enabled: form.slippage_enabled,
      taker_fee_rate: Number(form.taker_fee_rate),
      slippage_min_usd: Number(form.slippage_min_usd),
      slippage_max_usd: Number(form.slippage_max_usd),
      profit_target_pct: form.profit_target_pct
        ? normalizePercent(form.profit_target_pct, 0)
        : null,
      latency_enabled: form.latency_enabled,
      latency_min_sec: Number(form.latency_min_sec),
      latency_max_sec: Number(form.latency_max_sec),
      dynamic_tp_enabled: form.dynamic_tp_enabled,
      webhook_passthrough_enabled: form.webhook_passthrough_enabled,
      webhook_passthrough_url: form.webhook_passthrough_url.trim() || null
    };

    const res = await fetch("/api/evals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) return;
    const data = await res.json();
    upsertEval(data);
    setCreatedId(data.id);
  };

  const webhookUrl = typeof window !== "undefined" ? `${window.location.origin}/api/webhook/${form.strategy_key}` : "";

  return (
    <Dialog open={open} onOpenChange={(next) => {
      setOpen(next);
      if (!next) setCreatedId(null);
    }}>
      <DialogTrigger asChild>
        <Button variant="outline">New Eval</Button>
      </DialogTrigger>
      <DialogContent className="h-[90vh] w-[95vw] max-w-lg overflow-hidden p-0 sm:h-auto sm:w-full sm:max-w-2xl">
        <div className="flex h-full flex-col">
          <DialogHeader className="px-5 pt-5">
            <DialogTitle>Create new eval</DialogTitle>
            <DialogDescription>Spin up a simulated eval account in seconds.</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto px-5 pb-6">
            <div className="grid gap-4">
              <div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Name</div>
                <Input
                  placeholder="Name"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Strategy key</div>
                <Input
                  placeholder="Strategy key"
                  value={form.strategy_key}
                  onChange={(event) => setForm({ ...form, strategy_key: event.target.value })}
                />
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Symbol</div>
                <Select
                  value={form.symbol}
                  onValueChange={(value) => setForm({ ...form, symbol: value })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Symbol" />
                  </SelectTrigger>
                  <SelectContent position="popper" side="bottom" align="start" sideOffset={6}>
                  <SelectItem value="BTC">BTC</SelectItem>
                  <SelectItem value="ETH">ETH</SelectItem>
                  <SelectItem value="SOL">SOL</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Starting balance</div>
                <Input
                  type="number"
                  inputMode="decimal"
                  placeholder="Starting balance"
                  value={form.starting_balance}
                  onChange={(event) => setForm({ ...form, starting_balance: event.target.value })}
                />
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Fixed risk USD</div>
                <Input
                  type="number"
                  inputMode="decimal"
                  placeholder="Fixed risk USD (e.g. 50)"
                  value={form.risk_usd}
                  onChange={(event) => setForm({ ...form, risk_usd: event.target.value })}
                />
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Max DD %</div>
                  <Input
                    type="number"
                    inputMode="decimal"
                    placeholder="Max DD % (6)"
                    value={form.max_dd_pct}
                    onChange={(event) => setForm({ ...form, max_dd_pct: event.target.value })}
                  />
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Daily DD %</div>
                  <Input
                    type="number"
                    inputMode="decimal"
                    placeholder="Daily DD % (3)"
                    value={form.daily_dd_pct}
                    onChange={(event) => setForm({ ...form, daily_dd_pct: event.target.value })}
                  />
                </div>
              </div>
              <details className="rounded-lg border border-border/70 bg-panelSoft/60 p-3">
                <summary className="cursor-pointer text-sm font-medium text-slate-200">
                  Advanced settings
                </summary>
                <div className="mt-4 grid gap-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <Button
                      variant={form.fees_enabled ? "default" : "outline"}
                      onClick={() => setForm({ ...form, fees_enabled: !form.fees_enabled })}
                    >
                      Fees {form.fees_enabled ? "ON" : "OFF"}
                    </Button>
                    <Button
                      variant={form.slippage_enabled ? "default" : "outline"}
                      onClick={() => setForm({ ...form, slippage_enabled: !form.slippage_enabled })}
                    >
                      Slippage {form.slippage_enabled ? "ON" : "OFF"}
                    </Button>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Taker fee</div>
                      <Input
                        type="number"
                        inputMode="decimal"
                        placeholder="Taker fee (0.0004)"
                        value={form.taker_fee_rate}
                        onChange={(event) => setForm({ ...form, taker_fee_rate: event.target.value })}
                      />
                    </div>
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Slip min</div>
                      <Input
                        type="number"
                        inputMode="decimal"
                        placeholder="Slip min (2)"
                        value={form.slippage_min_usd}
                        onChange={(event) => setForm({ ...form, slippage_min_usd: event.target.value })}
                      />
                    </div>
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Slip max</div>
                      <Input
                        type="number"
                        inputMode="decimal"
                        placeholder="Slip max (20)"
                        value={form.slippage_max_usd}
                        onChange={(event) => setForm({ ...form, slippage_max_usd: event.target.value })}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Order latency</div>
                      <Button
                        variant={form.latency_enabled ? "default" : "outline"}
                        onClick={() => setForm({ ...form, latency_enabled: !form.latency_enabled })}
                      >
                        Latency {form.latency_enabled ? "ON" : "OFF"}
                      </Button>
                      <div className="text-[11px] text-slate-500 mt-1">Simulate bot placement time.</div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Min sec</div>
                        <Input
                          type="number"
                          inputMode="decimal"
                          placeholder="Min sec (2)"
                          value={form.latency_min_sec}
                          onChange={(event) => setForm({ ...form, latency_min_sec: event.target.value })}
                        />
                      </div>
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Max sec</div>
                        <Input
                          type="number"
                          inputMode="decimal"
                          placeholder="Max sec (10)"
                          value={form.latency_max_sec}
                          onChange={(event) => setForm({ ...form, latency_max_sec: event.target.value })}
                        />
                      </div>
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">Profit target %</div>
                    <Input
                      type="number"
                      inputMode="decimal"
                      placeholder="Profit target % (e.g. 10)"
                      value={form.profit_target_pct}
                      onChange={(event) => setForm({ ...form, profit_target_pct: event.target.value })}
                    />
                  </div>
                  <div className="rounded-lg border border-border/70 bg-panel/70 p-3">
                    <label className="flex items-start gap-3 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1 h-4 w-4 accent-neon"
                        checked={form.dynamic_tp_enabled}
                        onChange={(event) => setForm({ ...form, dynamic_tp_enabled: event.target.checked })}
                      />
                      <div>
                        <div className="font-medium">Dynamic TP (webhook exits)</div>
                        <div className="text-xs text-slate-500">
                          When enabled, TP in entry webhooks is ignored. Positions exit only via exit webhook.
                        </div>
                      </div>
                    </label>
                  </div>
                  <div className="rounded-lg border border-border/70 bg-panel/70 p-3 space-y-3">
                    <label className="flex items-start gap-3 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1 h-4 w-4 accent-neon"
                        checked={form.webhook_passthrough_enabled}
                        onChange={(event) =>
                          setForm({ ...form, webhook_passthrough_enabled: event.target.checked })
                        }
                      />
                      <div>
                        <div className="font-medium">Webhook Passthrough</div>
                        <div className="text-xs text-slate-500">
                          Forward each incoming webhook payload unchanged to your full internal URL.
                        </div>
                      </div>
                    </label>
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-1">
                        Passthrough URL (full URL)
                      </div>
                      <Input
                        placeholder="http://10.0.0.15:9000/hooks/tradingview"
                        value={form.webhook_passthrough_url}
                        onChange={(event) =>
                          setForm({ ...form, webhook_passthrough_url: event.target.value })
                        }
                      />
                    </div>
                  </div>
                </div>
              </details>
              {createdId && (
                <div className="rounded-lg border border-border/80 bg-panelSoft/60 p-4 text-sm text-slate-300">
                  <p className="text-neon">Eval created</p>
                  <p className="mt-2">Webhook URL</p>
                  <p className="break-all text-xs text-slate-400">{webhookUrl}</p>
                  <p className="mt-2">TradingView JSON</p>
                  <pre className="mt-2 text-xs text-slate-400">
{`{\n  "ticker": "${form.symbol}USDT",\n  "side": "LONG",\n  "entry": 44000,\n  "stop": 42000,\n  "tp": 46000\n}`}
                  </pre>
                </div>
              )}
            </div>
          </div>
          <div className="border-t border-border/70 bg-panel/80 px-5 py-4">
            <Button className="w-full" onClick={handleSubmit}>
              Create Eval
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
