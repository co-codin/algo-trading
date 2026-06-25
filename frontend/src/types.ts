export type Mode = "landing" | "live" | "breadth" | "quant" | "feedback" | "profile" | "admin";

export type AuthUser = {
  id: number;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  activated_at: string | null;
  expired_at: string | null;
  free_trial_end_at: string | null;
  first_name: string | null;
  last_name: string | null;
  middle_name: string | null;
};

export type AuthMePayload = {
  ok: true;
  user: AuthUser | null;
};

export type AuthPayload = {
  ok: true;
  user: AuthUser;
};

export type AdminUsersPayload = {
  ok: true;
  users: AuthUser[];
};

export type PlatformSettings = {
  is_free_trial_enabled: boolean;
};

export type PlatformSettingsPayload = {
  ok: true;
  settings: PlatformSettings;
};

export type FeedbackStatus = "open" | "in_progress" | "resolved";

export type FeedbackItem = {
  id: number;
  user_id: number;
  username: string;
  title: string;
  description: string;
  status: FeedbackStatus;
  created_at: string;
  updated_at: string;
};

export type FeedbackPayload = {
  ok: true;
  feedback: FeedbackItem;
};

export type AdminFeedbackPayload = {
  ok: true;
  feedback: FeedbackItem[];
};

export type StrategyInfo = {
  name: string;
  description: string;
};

export type StrategyPayload = {
  ok: true;
  strategies: StrategyInfo[];
  presets: string[];
};

export type QuantStrategyIdea = {
  id: string;
  title: string;
  group: string;
  action: "bullish" | "bearish" | "neutral";
  score: number;
  confidence: "low" | "medium" | "high";
  metrics: Record<string, string | number>;
  reasons: string[];
};

export type QuantStrategiesPayload = {
  ok: true;
  market: string;
  symbol: string;
  interval: string;
  candles: Candle[];
  signals: Marker[];
  indicators: IndicatorDefinition[];
  ideas: QuantStrategyIdea[];
};

export type SymbolInfo = {
  symbol: string;
  base_asset: string;
  quote_volume: number;
  last_price: number;
};

export type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type Marker = {
  time: number;
  price: number;
  type: string;
  reason: string;
};

export type IndicatorPoint = {
  time: number;
  value: number;
  color?: string;
};

export type IndicatorSeries = {
  id: string;
  label: string;
  type: "line" | "histogram";
  color: string;
  points: IndicatorPoint[];
};

export type IndicatorDefinition = {
  id: string;
  label: string;
  pane: "price" | "volume" | "oscillator";
  default_visible: boolean;
  series: IndicatorSeries[];
};

export type MarketEvent = {
  id: string;
  type: string;
  market: string;
  symbol: string;
  title: string;
  description: string;
  details: string;
  severity: "low" | "medium" | "high" | "info" | "warning" | "critical";
  time: number | string | null;
  source: string;
  metrics: Record<string, string | number | null>;
};

export type LiveChartPayload = {
  ok: true;
  market: string;
  data_source: string;
  symbol: string;
  interval: string;
  strategy: string | null;
  candles: Candle[];
  signals: Marker[];
  rsi_alert_signal: Marker | null;
  indicators: IndicatorDefinition[];
  events: MarketEvent[];
};

export type LiveSymbolsPayload = {
  ok: true;
  symbols: Record<string, Array<{ value: string; label: string }>>;
};

export type MarketBreadthItem = {
  symbol: string;
  label: string;
  period: string;
  data: string;
};

export type MarketBreadthGroup = {
  name: string;
  items: MarketBreadthItem[];
};

export type MarketBreadthBar = Candle & {
  date: string;
};

export type MarketBreadthSeries = {
  symbol: string;
  label: string;
  period: string;
  data: string;
  candles: MarketBreadthBar[];
};

export type MarketBreadthPayload = {
  ok: true;
  source: string;
  groups: MarketBreadthGroup[];
  series: Record<string, MarketBreadthSeries>;
  put_call_symbol: string;
  updated_at: string;
};

export type SavedWorkspace = {
  id: string;
  name: string;
  market: string;
  symbol: string;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type SavedWorkspacesPayload = {
  ok: true;
  workspaces: SavedWorkspace[];
};

export type SavedWatchlist = {
  id: string;
  name: string;
  market: string;
  symbols: string[];
  created_at: string;
  updated_at: string;
};

export type SavedWatchlistsPayload = {
  ok: true;
  watchlists: SavedWatchlist[];
};
