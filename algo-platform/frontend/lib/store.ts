import { create } from "zustand";

export type Price = {
  ts: string;
  source: string;
  price: number;
};

export type EvalSummary = {
  id: string;
  name: string;
  strategy_key: string;
  strategy_name?: string | null;
  account_type?: string;
  prop_firm_mode?: string | null;
  symbol: string;
  status: string;
  current_equity: number;
  current_balance: number;
  starting_balance: number;
  day_start_equity: number;
  max_dd_pct: number;
  daily_dd_pct: number;
  dynamic_tp_enabled?: boolean;
  webhook_passthrough_enabled?: boolean;
  webhook_passthrough_url?: string | null;
  last_price?: number | null;
  open_pnl?: number | null;
  unrealized_equity?: number | null;
  has_open_position: boolean;
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
  daily_reset_at_ts?: string | null;
  daily_reset_seconds_remaining?: number | null;
  risk_usd?: number | null;
  average_rr?: number | null;
  avg_win_r?: number | null;
  win_rate_r?: number | null;
  n_valid_r?: number | null;
  n_wins_r?: number | null;
  expectancy_r?: number | null;
  profit_target_pct?: number | null;
  profit_target_equity?: number | null;
  profit_remaining_usd?: number | null;
  profit_progress_pct?: number | null;
  passed_at?: string | null;
  archived_at?: string | null;
  wins?: number | null;
  losses?: number | null;
  breakeven?: number | null;
  win_rate_pct?: number | null;
  profit_factor?: number | null;
  rolling_avg_pnl_per_trade?: number | null;
  expected_trades_to_pass?: number | null;
  expected_days_to_pass?: number | null;
  expected_trades_to_daily_fail?: number | null;
  expected_trades_to_max_fail?: number | null;
};

type StoreState = {
  prices: Record<string, Price>;
  evals: Record<string, EvalSummary>;
  wsConnected: boolean;
  setPrices: (prices: Record<string, Price>) => void;
  updatePrice: (symbol: string, price: Price) => void;
  setEvals: (evals: EvalSummary[]) => void;
  upsertEval: (evalSummary: EvalSummary) => void;
  patchEval: (id: string, patch: Partial<EvalSummary>) => void;
  setWsConnected: (value: boolean) => void;
};

export const useRealtimeStore = create<StoreState>((set) => ({
  prices: {},
  evals: {},
  wsConnected: false,
  setPrices: (prices) =>
    set(() => ({
      prices
    })),
  updatePrice: (symbol, price) =>
    set((state) => ({
      prices: { ...state.prices, [symbol]: price }
    })),
  setEvals: (evals) =>
    set(() => ({
      evals: evals.reduce((acc, evalSummary) => {
        acc[evalSummary.id] = evalSummary;
        return acc;
      }, {} as Record<string, EvalSummary>)
    })),
  upsertEval: (evalSummary) =>
    set((state) => ({
      evals: { ...state.evals, [evalSummary.id]: evalSummary }
    })),
  patchEval: (id, patch) =>
    set((state) => ({
      evals: { ...state.evals, [id]: { ...(state.evals[id] ?? {}), ...patch } }
    })),
  setWsConnected: (value) => set(() => ({ wsConnected: value }))
}));
