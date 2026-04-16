"use client";

import { useMemo, useState } from "react";
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
import type { StrategySummary } from "@/lib/strategies";

const defaultPayload = {
  max_dd_pct: 6,
  daily_dd_pct: 3
};

type NewEvalModalProps = {
  strategies: StrategySummary[];
};

export function NewEvalModal({ strategies }: NewEvalModalProps) {
  const upsertEval = useRealtimeStore((s) => s.upsertEval);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    strategy_key: "",
    account_type: "REGULAR",
    prop_firm_mode: "EVAL",
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
    dynamic_tp_enabled: false
  });

  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.key === form.strategy_key) ?? null,
    [strategies, form.strategy_key]
  );

  const normalizePercent = (value: string, fallback: number) => {
    const parsed = Number(value);
    if (Number.isNaN(parsed)) return fallback / 100;
    return parsed > 1 ? parsed / 100 : parsed;
  };

  const resetState = () => {
    setCreatedId(null);
    setError(null);
  };

  const handleSubmit = async () => {
    setError(null);
    if (!form.strategy_key) {
      setError("Choose a strategy first.");
      return;
    }
    const payload = {
      name: form.name,
      strategy_key: form.strategy_key,
      account_type: form.account_type,
      prop_firm_mode: form.account_type === "PROP_FIRM" ? form.prop_firm_mode : null,
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
      dynamic_tp_enabled: form.dynamic_tp_enabled
    };

    const res = await fetch("/api/evals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setError(data?.reason ?? "Failed to create sim account.");
      return;
    }
    const data = await res.json();
    upsertEval(data);
    setCreatedId(data.id);
  };

  const webhookUrl = typeof window !== "undefined" && selectedStrategy
    ? `${window.location.origin}/api/webhook/${selectedStrategy.key}`
    : "";

  return (
    <Dialog open={open} onOpenChange={(next) => {
      setOpen(next);
      if (!next) resetState();
    }}>
      <DialogTrigger asChild>
        <Button variant="outline" disabled={!strategies.length}>New Sim Account</Button>
      </DialogTrigger>
      <DialogContent className="h-[90vh] w-[95vw] max-w-lg overflow-hidden p-0 sm:h-auto sm:w-full sm:max-w-2xl">
        <div className="flex h-full flex-col">
          <DialogHeader className="px-5 pt-5">
            <DialogTitle>Create sim account</DialogTitle>
            <DialogDescription>
              Attach the sim account to a stored strategy. Strategy routing owns ticker and webhook configuration.
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto px-5 pb-6">
            <div className="grid gap-4">
              {!strategies.length ? (
                <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-slate-200">
                  Create a strategy in the Strategies tab before creating a sim account.
                </div>
              ) : null}
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Name</div>
                <Input
                  placeholder="Name"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </div>
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Account type</div>
                <div className="flex flex-wrap gap-2">
                  {[
                    { value: "REGULAR", label: "Regular Account" },
                    { value: "PROP_FIRM", label: "Prop Firm" }
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={
                        form.account_type === option.value
                          ? "rounded-full border border-neon/60 bg-neon/10 px-3 py-2 text-sm text-neon"
                          : "rounded-full border border-border/70 px-3 py-2 text-sm text-slate-400 hover:text-slate-100"
                      }
                      onClick={() => setForm({ ...form, account_type: option.value })}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              {form.account_type === "PROP_FIRM" ? (
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Prop firm mode</div>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { value: "EVAL", label: "Eval" },
                      { value: "LIVE_SIM", label: "Live Sim" }
                    ].map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        className={
                          form.prop_firm_mode === option.value
                            ? "rounded-full border border-neon/60 bg-neon/10 px-3 py-2 text-sm text-neon"
                            : "rounded-full border border-border/70 px-3 py-2 text-sm text-slate-400 hover:text-slate-100"
                        }
                        onClick={() => setForm({ ...form, prop_firm_mode: option.value })}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Strategy</div>
                <Select
                  value={form.strategy_key}
                  onValueChange={(value) => setForm({ ...form, strategy_key: value })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Choose strategy" />
                  </SelectTrigger>
                  <SelectContent position="popper" side="bottom" align="start" sideOffset={6}>
                    {strategies.map((strategy) => (
                      <SelectItem key={strategy.key} value={strategy.key}>
                        {strategy.name} ({strategy.key})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {selectedStrategy ? (
                <div className="rounded-lg border border-border/70 bg-panelSoft/60 p-3 text-sm">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Strategy Webhook</div>
                  <div className="mt-2 text-slate-100 break-all">{webhookUrl}</div>
                  <div className="mt-2 text-xs text-slate-500">
                    Ticker: {selectedStrategy.symbol}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    Passthrough: {selectedStrategy.webhook_passthrough_enabled
                      ? selectedStrategy.webhook_passthrough_url || "(enabled, URL not set)"
                      : "Disabled"}
                  </div>
                </div>
              ) : null}
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Starting balance</div>
                <Input
                  type="number"
                  inputMode="decimal"
                  placeholder="Starting balance"
                  value={form.starting_balance}
                  onChange={(event) => setForm({ ...form, starting_balance: event.target.value })}
                />
              </div>
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Fixed risk USD</div>
                <Input
                  type="number"
                  inputMode="decimal"
                  placeholder="Fixed risk USD"
                  value={form.risk_usd}
                  onChange={(event) => setForm({ ...form, risk_usd: event.target.value })}
                />
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Max DD %</div>
                  <Input
                    type="number"
                    inputMode="decimal"
                    value={form.max_dd_pct}
                    onChange={(event) => setForm({ ...form, max_dd_pct: event.target.value })}
                  />
                </div>
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Daily DD %</div>
                  <Input
                    type="number"
                    inputMode="decimal"
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
                      type="button"
                      variant={form.fees_enabled ? "default" : "outline"}
                      onClick={() => setForm({ ...form, fees_enabled: !form.fees_enabled })}
                    >
                      Fees {form.fees_enabled ? "ON" : "OFF"}
                    </Button>
                    <Button
                      type="button"
                      variant={form.slippage_enabled ? "default" : "outline"}
                      onClick={() => setForm({ ...form, slippage_enabled: !form.slippage_enabled })}
                    >
                      Slippage {form.slippage_enabled ? "ON" : "OFF"}
                    </Button>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Taker fee</div>
                      <Input
                        type="number"
                        inputMode="decimal"
                        value={form.taker_fee_rate}
                        onChange={(event) => setForm({ ...form, taker_fee_rate: event.target.value })}
                      />
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Slip min</div>
                      <Input
                        type="number"
                        inputMode="decimal"
                        value={form.slippage_min_usd}
                        onChange={(event) => setForm({ ...form, slippage_min_usd: event.target.value })}
                      />
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Slip max</div>
                      <Input
                        type="number"
                        inputMode="decimal"
                        value={form.slippage_max_usd}
                        onChange={(event) => setForm({ ...form, slippage_max_usd: event.target.value })}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Order latency</div>
                      <Button
                        type="button"
                        variant={form.latency_enabled ? "default" : "outline"}
                        onClick={() => setForm({ ...form, latency_enabled: !form.latency_enabled })}
                      >
                        Latency {form.latency_enabled ? "ON" : "OFF"}
                      </Button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Min sec</div>
                        <Input
                          type="number"
                          inputMode="decimal"
                          value={form.latency_min_sec}
                          onChange={(event) => setForm({ ...form, latency_min_sec: event.target.value })}
                        />
                      </div>
                      <div>
                        <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Max sec</div>
                        <Input
                          type="number"
                          inputMode="decimal"
                          value={form.latency_max_sec}
                          onChange={(event) => setForm({ ...form, latency_max_sec: event.target.value })}
                        />
                      </div>
                    </div>
                  </div>
                  <div>
                    <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Profit target %</div>
                    <Input
                      type="number"
                      inputMode="decimal"
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
                        <div className="font-medium">Dynamic TP</div>
                        <div className="text-xs text-slate-500">
                          Ignore TP from entry webhooks and exit only through later exit signals.
                        </div>
                      </div>
                    </label>
                  </div>
                </div>
              </details>
              {error ? (
                <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-slate-100">
                  {error}
                </div>
              ) : null}
              {createdId && selectedStrategy ? (
                <div className="rounded-lg border border-border/80 bg-panelSoft/60 p-4 text-sm text-slate-300">
                  <p className="text-neon">Sim account created</p>
                  <p className="mt-2 text-xs text-slate-500">
                    {form.account_type === "REGULAR"
                      ? "Regular account"
                      : `Prop firm • ${form.prop_firm_mode === "LIVE_SIM" ? "Live Sim" : "Eval"}`}
                  </p>
                  <p className="mt-2">Webhook URL</p>
                  <p className="break-all text-xs text-slate-400">{webhookUrl}</p>
                  <p className="mt-2">TradingView JSON</p>
                  <pre className="mt-2 text-xs text-slate-400">
{`{\n  "ticker": "${selectedStrategy.symbol}USDT",\n  "side": "LONG",\n  "entry": 44000,\n  "stop": 42000,\n  "tp": 46000\n}`}
                  </pre>
                </div>
              ) : null}
            </div>
          </div>
          <div className="border-t border-border/70 bg-panel/80 px-5 py-4">
            <Button className="w-full" onClick={handleSubmit} disabled={!strategies.length}>
              Create Sim Account
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
