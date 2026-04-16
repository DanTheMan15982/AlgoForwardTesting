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
import { Badge } from "@/components/ui/badge";
import type { StrategySummary } from "@/lib/strategies";

type StrategyListProps = {
  strategies: StrategySummary[];
  activeEvalCounts: Record<string, number>;
  onCreated: (strategy: StrategySummary) => void;
  onUpdated: (strategy: StrategySummary) => void;
};

type StrategyFormState = {
  key: string;
  name: string;
  symbol: string;
  webhook_passthrough_enabled: boolean;
  webhook_passthrough_url: string;
};

const emptyForm: StrategyFormState = {
  key: "",
  name: "",
  symbol: "BTC",
  webhook_passthrough_enabled: false,
  webhook_passthrough_url: ""
};

export function StrategyList({ strategies, activeEvalCounts, onCreated, onUpdated }: StrategyListProps) {
  const [open, setOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [form, setForm] = useState<StrategyFormState>(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const sortedStrategies = useMemo(
    () => [...strategies].sort((a, b) => a.name.localeCompare(b.name) || a.key.localeCompare(b.key)),
    [strategies]
  );

  const selected = editingKey
    ? strategies.find((strategy) => strategy.key === editingKey) ?? null
    : null;

  const resetForm = () => {
    setEditingKey(null);
    setForm(emptyForm);
    setError(null);
  };

  const openCreate = () => {
    resetForm();
    setOpen(true);
  };

  const openEdit = (strategy: StrategySummary) => {
    setEditingKey(strategy.key);
    setForm({
      key: strategy.key,
      name: strategy.name,
      webhook_passthrough_enabled: strategy.webhook_passthrough_enabled,
      symbol: strategy.symbol,
      webhook_passthrough_url: strategy.webhook_passthrough_url ?? ""
    });
    setError(null);
    setOpen(true);
  };

  const handleSubmit = async () => {
    setError(null);
    const payload = {
      name: form.name.trim(),
      symbol: form.symbol,
      webhook_passthrough_enabled: form.webhook_passthrough_enabled,
      webhook_passthrough_url: form.webhook_passthrough_url.trim() || null
    };

    const isEditing = Boolean(editingKey);
    const url = isEditing ? `/api/strategies/${editingKey}` : "/api/strategies";
    const body = isEditing
      ? payload
      : { key: form.key.trim(), ...payload };

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setError(data?.reason ?? "Failed to save strategy.");
      return;
    }
    const data = await res.json();
    if (isEditing) {
      onUpdated(data);
    } else {
      onCreated(data);
    }
    setOpen(false);
    resetForm();
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-neonSoft">Strategies</p>
          <h2 className="text-2xl font-semibold text-slate-100">Webhook routing lives here</h2>
          <p className="mt-1 text-sm text-slate-500">
            Define the strategy key once, set the passthrough once, and attach as many sim accounts as you want.
          </p>
        </div>
        <Dialog open={open} onOpenChange={(next) => {
          setOpen(next);
          if (!next) resetForm();
        }}>
          <DialogTrigger asChild>
            <Button variant="outline" onClick={openCreate}>New Strategy</Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>{editingKey ? "Edit strategy" : "Create strategy"}</DialogTitle>
              <DialogDescription>
                Strategy keys are what your incoming webhooks target.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4">
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Key</div>
                <Input
                  value={form.key}
                  disabled={Boolean(editingKey)}
                  placeholder="ema_retest_v1"
                  onChange={(event) => setForm({ ...form, key: event.target.value })}
                />
              </div>
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Name</div>
                <Input
                  value={form.name}
                  placeholder="EMA Retest"
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </div>
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Ticker</div>
                <div className="flex gap-2">
                  {(["BTC", "ETH", "SOL"] as const).map((symbol) => (
                    <button
                      key={symbol}
                      type="button"
                      className={
                        form.symbol === symbol
                          ? "rounded-full border border-neon/60 bg-neon/10 px-3 py-2 text-sm text-neon"
                          : "rounded-full border border-border/70 px-3 py-2 text-sm text-slate-400 hover:text-slate-100"
                      }
                      onClick={() => setForm({ ...form, symbol })}
                    >
                      {symbol}
                    </button>
                  ))}
                </div>
              </div>
              <label className="flex items-start gap-3 rounded-lg border border-border/70 bg-panelSoft/60 p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-neon"
                  checked={form.webhook_passthrough_enabled}
                  onChange={(event) => setForm({ ...form, webhook_passthrough_enabled: event.target.checked })}
                />
                <div>
                  <div className="font-medium">Webhook passthrough</div>
                  <div className="text-xs text-slate-500">
                    Forward each webhook payload unchanged to a full internal URL.
                  </div>
                </div>
              </label>
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">Passthrough URL</div>
                <Input
                  value={form.webhook_passthrough_url}
                  placeholder="http://10.0.0.15:9000/hooks/tradingview"
                  onChange={(event) => setForm({ ...form, webhook_passthrough_url: event.target.value })}
                />
              </div>
              {selected && typeof window !== "undefined" ? (
                <div className="rounded-lg border border-border/70 bg-panelSoft/60 p-3 text-xs text-slate-400">
                  Public webhook: {window.location.origin}/api/webhook/{selected.key}
                </div>
              ) : null}
              {error ? (
                <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-slate-100">
                  {error}
                </div>
              ) : null}
              <Button onClick={handleSubmit}>{editingKey ? "Save Strategy" : "Create Strategy"}</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid gap-4">
        {sortedStrategies.length ? sortedStrategies.map((strategy) => (
          <div
            key={strategy.key}
            className="rounded-xl border border-border/70 bg-panel/75 p-4 shadow-glowSoft"
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-lg font-semibold text-slate-100">{strategy.name}</h3>
                  <Badge variant="default">{strategy.key}</Badge>
                  <Badge variant="info">{strategy.symbol}</Badge>
                  <Badge variant={strategy.webhook_passthrough_enabled ? "success" : "warning"}>
                    {strategy.webhook_passthrough_enabled ? "Passthrough On" : "Passthrough Off"}
                  </Badge>
                </div>
                <div className="text-sm text-slate-400 break-all">
                  Webhook: {typeof window !== "undefined" ? `${window.location.origin}/api/webhook/${strategy.key}` : `/api/webhook/${strategy.key}`}
                </div>
                <div className="text-sm text-slate-500 break-all">
                  Forward to: {strategy.webhook_passthrough_enabled
                    ? strategy.webhook_passthrough_url || "(enabled, URL not set)"
                    : "Disabled"}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="rounded-lg border border-border/60 bg-panelSoft/60 px-3 py-2 text-sm text-slate-300">
                  Active sim accounts: {activeEvalCounts[strategy.key] ?? 0}
                </div>
                <Button variant="outline" onClick={() => openEdit(strategy)}>
                  Edit
                </Button>
              </div>
            </div>
          </div>
        )) : (
          <div className="rounded-xl border border-border/70 bg-panel/75 p-6 text-sm text-slate-400">
            No strategies yet. Create one before spinning up sim accounts.
          </div>
        )}
      </div>
    </div>
  );
}
