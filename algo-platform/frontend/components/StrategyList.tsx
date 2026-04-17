"use client";

import { useEffect, useMemo, useState } from "react";
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
import { tradingviewTickerForInstrument, exchangeFeedLabel, type MatrixInstrument } from "@/lib/instruments";
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
  const [instrumentQuery, setInstrumentQuery] = useState("");
  const [instruments, setInstruments] = useState<MatrixInstrument[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      const res = await fetch("/api/market-data/matrix");
      if (!res.ok) return;
      setInstruments(await res.json());
    };
    load();
  }, []);

  const sortedStrategies = useMemo(
    () => [...strategies].sort((a, b) => a.name.localeCompare(b.name) || a.key.localeCompare(b.key)),
    [strategies]
  );

  const selected = editingKey
    ? strategies.find((strategy) => strategy.key === editingKey) ?? null
    : null;

  const instrumentsById = useMemo(
    () => Object.fromEntries(instruments.map((row) => [row.instrument_id, row])),
    [instruments]
  );

  const selectedInstrument = form.symbol ? instrumentsById[form.symbol] ?? null : null;

  const filteredInstruments = useMemo(() => {
    const normalizedQuery = instrumentQuery.trim().toLowerCase();
    const ranked = [...instruments].sort((a, b) => {
      const aLive = a.current_price != null ? 0 : 1;
      const bLive = b.current_price != null ? 0 : 1;
      return aLive - bLive || a.instrument_id.localeCompare(b.instrument_id);
    });
    if (!normalizedQuery) {
      return ranked.slice(0, 40);
    }
    return ranked
      .filter((row) => {
        const tvTicker = tradingviewTickerForInstrument(row).toLowerCase();
        return (
          row.instrument_id.toLowerCase().includes(normalizedQuery) ||
          row.display_name.toLowerCase().includes(normalizedQuery) ||
          row.exchange.toLowerCase().includes(normalizedQuery) ||
          row.market.toLowerCase().includes(normalizedQuery) ||
          tvTicker.includes(normalizedQuery)
        );
      })
      .slice(0, 40);
  }, [instrumentQuery, instruments]);

  const resetForm = () => {
    setEditingKey(null);
    setForm(emptyForm);
    setError(null);
    setInstrumentQuery("");
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
    setInstrumentQuery("");
    setOpen(true);
  };

  const handleSubmit = async () => {
    setError(null);
    if (!form.name.trim()) {
      setError("Strategy name is required.");
      return;
    }
    if (!form.symbol.trim()) {
      setError("Pick an instrument before saving.");
      return;
    }
    if (!editingKey && !form.key.trim()) {
      setError("Strategy key is required.");
      return;
    }
    const payload = {
      name: form.name.trim(),
      symbol: form.symbol,
      webhook_passthrough_enabled: form.webhook_passthrough_enabled,
      webhook_passthrough_url: form.webhook_passthrough_url.trim() || null
    };

    const isEditing = Boolean(editingKey);
    const url = isEditing ? `/api/strategies/${editingKey}` : "/api/strategies";
    const body = isEditing ? payload : { key: form.key.trim(), ...payload };

    setSaving(true);
    try {
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
    } finally {
      setSaving(false);
    }
  };

  const saveDisabled = saving || !form.name.trim() || !form.symbol.trim() || (!editingKey && !form.key.trim());

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-neonSoft">Strategies</p>
          <h2 className="text-2xl font-semibold text-slate-100">Webhook routing lives here</h2>
          <p className="mt-1 text-sm text-slate-500">
            Keep the strategy key stable, route it to one feed instrument, and reuse it across sim accounts.
          </p>
        </div>
        <Dialog
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) resetForm();
          }}
        >
          <DialogTrigger asChild>
            <Button variant="outline" onClick={openCreate}>New Strategy</Button>
          </DialogTrigger>
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle>{editingKey ? "Edit strategy" : "Create strategy"}</DialogTitle>
              <DialogDescription>
                Choose one concrete instrument. The strategy will only accept webhook tickers that map to that feed.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4">
              <div className="grid gap-4 rounded-xl border border-border/70 bg-panelSoft/40 p-4 md:grid-cols-2">
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
              </div>

              <div className="rounded-xl border border-border/70 bg-panelSoft/40 p-4">
                <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Instrument</div>
                    <div className="mt-1 text-sm text-slate-400">
                      Search by TradingView-style code, exchange, or instrument id.
                    </div>
                  </div>
                  <div className="text-xs text-slate-500">
                    Showing {filteredInstruments.length} result{filteredInstruments.length === 1 ? "" : "s"}
                  </div>
                </div>
                <div className="grid gap-3">
                  <Input
                    value={instrumentQuery}
                    placeholder="Search BTCUSD, BTCUSDT.P, OKX, Bybit..."
                    onChange={(event) => setInstrumentQuery(event.target.value)}
                  />
                  {selectedInstrument ? (
                    <div className="rounded-lg border border-neon/40 bg-neon/10 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Selected Ticker</div>
                          <div className="mt-1 font-mono text-sm text-slate-100">
                            {tradingviewTickerForInstrument(selectedInstrument)}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="info">{exchangeFeedLabel(selectedInstrument)}</Badge>
                          <Badge variant="default">{selectedInstrument.instrument_id}</Badge>
                        </div>
                      </div>
                      <div className="mt-3 grid gap-3 text-xs md:grid-cols-2">
                        <div>
                          <div className="uppercase tracking-[0.18em] text-slate-500">Display Name</div>
                          <div className="mt-1 text-slate-300">{selectedInstrument.display_name}</div>
                        </div>
                        <div>
                          <div className="uppercase tracking-[0.18em] text-slate-500">Exchange Feed</div>
                          <div className="mt-1 text-slate-300">{selectedInstrument.exchange}</div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed border-border/70 bg-panel/40 px-4 py-3 text-sm text-slate-500">
                      Pick one instrument before saving the strategy.
                    </div>
                  )}
                  <div className="max-h-72 space-y-2 overflow-y-auto rounded-lg border border-border/70 bg-panelSoft/40 p-2">
                    {filteredInstruments.length ? (
                      filteredInstruments.map((instrument) => {
                        const isSelected = form.symbol === instrument.instrument_id;
                        return (
                          <button
                            key={instrument.instrument_id}
                            type="button"
                            className={
                              isSelected
                                ? "flex w-full items-start justify-between rounded-lg border border-neon/60 bg-neon/10 px-3 py-3 text-left"
                                : "flex w-full items-start justify-between rounded-lg border border-border/60 bg-panel/60 px-3 py-3 text-left hover:border-border"
                            }
                            onClick={() => setForm({ ...form, symbol: instrument.instrument_id })}
                          >
                            <div className="min-w-0">
                              <div className="font-mono text-sm text-slate-100">
                                {tradingviewTickerForInstrument(instrument)}
                              </div>
                              <div className="text-xs text-slate-400">{instrument.display_name}</div>
                            </div>
                            <div className="ml-3 flex shrink-0 flex-col items-end gap-1">
                              <Badge variant="info">{exchangeFeedLabel(instrument)}</Badge>
                              <span className="text-[11px] text-slate-500">{instrument.instrument_id}</span>
                            </div>
                          </button>
                        );
                      })
                    ) : (
                      <div className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-slate-500">
                        No instruments match that search.
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="grid gap-4 rounded-xl border border-border/70 bg-panelSoft/40 p-4">
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Routing</div>
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
              <Button onClick={handleSubmit} disabled={saveDisabled}>
                {saving ? "Saving..." : editingKey ? "Save Strategy" : "Create Strategy"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid gap-4">
        {sortedStrategies.length ? (
          sortedStrategies.map((strategy) => {
            const instrument = instrumentsById[strategy.symbol];
            return (
              <div
                key={strategy.key}
                className="rounded-xl border border-border/70 bg-panel/75 p-4 shadow-glowSoft"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-lg font-semibold text-slate-100">{strategy.name}</h3>
                      <Badge variant="default">{strategy.key}</Badge>
                      <Badge variant="info">
                        {instrument ? tradingviewTickerForInstrument(instrument) : strategy.symbol}
                      </Badge>
                      {instrument ? (
                        <Badge variant="default">{exchangeFeedLabel(instrument)}</Badge>
                      ) : null}
                      <Badge variant={strategy.webhook_passthrough_enabled ? "success" : "warning"}>
                        {strategy.webhook_passthrough_enabled ? "Passthrough On" : "Passthrough Off"}
                      </Badge>
                    </div>
                    <div className="grid gap-3 text-sm md:grid-cols-3">
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Feed Instrument</div>
                        <div className="mt-1 text-slate-300">{strategy.symbol}</div>
                      </div>
                      <div className="md:col-span-2">
                        <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Webhook</div>
                        <div className="mt-1 break-all text-slate-300">
                          {typeof window !== "undefined"
                            ? `${window.location.origin}/api/webhook/${strategy.key}`
                            : `/api/webhook/${strategy.key}`}
                        </div>
                      </div>
                      <div className="md:col-span-3">
                        <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Passthrough</div>
                        <div className="mt-1 break-all text-slate-400">
                          {strategy.webhook_passthrough_enabled
                            ? strategy.webhook_passthrough_url || "(enabled, URL not set)"
                            : "Disabled"}
                        </div>
                      </div>
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
            );
          })
        ) : (
          <div className="rounded-xl border border-border/70 bg-panel/75 p-6 text-sm text-slate-400">
            No strategies yet. Create one before spinning up sim accounts.
          </div>
        )}
      </div>
    </div>
  );
}
