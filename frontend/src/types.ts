export type Mode = "backtest" | "paper" | "live" | "runs" | "lab";

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
