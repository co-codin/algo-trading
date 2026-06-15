export type Mode = "live" | "breadth" | "lab" | "profile" | "admin";

export type AuthUser = {
  id: number;
  username: string;
  is_active: boolean;
  activated_at: string | null;
  expired_at: string | null;
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

export type StrategyInfo = {
  name: string;
  description: string;
};

export type StrategyPayload = {
  ok: true;
  strategies: StrategyInfo[];
  presets: string[];
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

export type LiveChartPayload = {
  ok: true;
  market: string;
  data_source: string;
  symbol: string;
  interval: string;
  strategy: string;
  candles: Candle[];
  signals: Marker[];
  paper_markers: Marker[];
};

export type RunSummary = {
  symbol?: string;
  initial_balance?: number;
  final_balance?: number;
  total_return_pct?: number;
  max_drawdown_pct?: number;
  trades?: number;
  win_rate?: number;
  profit_factor?: number | string;
  fee_total?: number;
  slippage_estimate?: number;
};

export type RunCard = {
  mode: string;
  path: string;
  timestamp: string;
  symbol: string;
  final_balance: number;
  summary: RunSummary;
};

export type RunDetails = {
  ok: true;
  path: string;
  summary: RunSummary;
  config: Record<string, string | number | boolean>;
  trades: Record<string, string>[];
  equity: Record<string, string>[];
};

export type StrategyLabRow = {
  rank: number;
  symbol: string;
  strategy: string;
  preset: string;
  final_balance: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  trades: number;
  win_rate: number;
  profit_factor: number | string;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_duration: number;
  average_trade_duration: number;
  exposure_pct: number;
  worst_trade: number;
  walk_forward_windows: number;
  walk_forward_avg_return_pct: number;
  walk_forward_worst_return_pct: number;
  walk_forward_best_return_pct: number;
  walk_forward_profitable_pct: number;
};

export type StrategyLabPayload = {
  ok: true;
  mode: "strategy-lab";
  rows: StrategyLabRow[];
};

export type CombinationSignalsPayload = {
  ok: true;
  mode: "combination-signals";
  market: string;
  data_source: string;
  symbol: string;
  interval: string;
  config: Record<string, string | number | boolean>;
  summary: RunSummary;
  candles: Candle[];
  signals: Marker[];
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
