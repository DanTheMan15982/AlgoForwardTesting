export type MatrixInstrument = {
  instrument_id: string;
  display_name: string;
  asset_class: string;
  market: string;
  exchange: string;
  provider: string;
  provider_type: string;
  external_ticker: string;
  stream_status: string;
  cadence_target: string;
  free_access: boolean;
  current_price?: number | null;
  price_ts?: string | null;
  price_source?: string | null;
  update_age_ms?: number | null;
  notes?: string | null;
};

export function tradingviewTickerForInstrument(row: Pick<MatrixInstrument, "external_ticker" | "market">): string {
  const normalized = row.external_ticker.replaceAll("-", "");
  if (row.market === "perp") {
    const noSwap = normalized.replace(/SWAP$/u, "");
    return `${noSwap}.P`;
  }
  if (normalized.endsWith("USDT")) {
    return `${normalized.slice(0, -4)}USD`;
  }
  return normalized;
}

export function exchangeFeedLabel(row: Pick<MatrixInstrument, "exchange" | "market">): string {
  return row.market === "perp" ? `${row.exchange} perp` : `${row.exchange} spot`;
}
