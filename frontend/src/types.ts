export type Mode = "live" | "breadth" | "profile" | "admin";

export type AuthUser = {
  id: number;
  username: string;
  is_active: boolean;
  is_admin: boolean;
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

export type LiveChartPayload = {
  ok: true;
  market: string;
  data_source: string;
  symbol: string;
  interval: string;
  strategy: string;
  candles: Candle[];
  signals: Marker[];
  indicators: IndicatorDefinition[];
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
