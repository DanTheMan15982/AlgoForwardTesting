export type StrategySummary = {
  key: string;
  name: string;
  symbol: string;
  created_at: string;
  updated_at: string;
  webhook_passthrough_enabled: boolean;
  webhook_passthrough_url?: string | null;
};
