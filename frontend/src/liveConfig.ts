import type { MessageKey } from "./i18n";

export type SelectOption = {
  label: string;
  value: string | number;
};

export type StrategyGroupDefinition = {
  id: string;
  labelKey: MessageKey;
  strategyNames: string[];
};

export const LIVE_WORKSPACE_STORAGE_KEY = "algoTradingLiveWorkspaces";

export const liveIntervalOptions = [
  { value: "1m", label: "1m" },
  { value: "3m", label: "3m" },
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "30m", label: "30m" },
  { value: "1h", label: "1h" },
  { value: "4h", label: "4h" },
  { value: "1d", label: "1d" },
  { value: "1w", label: "1w" },
  { value: "1M", label: "1M" },
] satisfies SelectOption[];

export const liveCandleOptions = [
  { value: 80, label: "80" },
  { value: 180, label: "180" },
  { value: 300, label: "300" },
  { value: 500, label: "500" },
  { value: 1000, label: "1000" },
] satisfies SelectOption[];

export const defaultLiveIndicators = ["ema", "vwap", "volume", "rsi", "macd"];

export const strategyGroupCatalog: StrategyGroupDefinition[] = [
  {
    id: "recommended",
    labelKey: "strategyGroups.recommended",
    strategyNames: [
      "ema-rsi",
      "macd",
      "supertrend",
      "adx-trend",
      "vwap-trend-continuation",
    ],
  },
  {
    id: "trend",
    labelKey: "strategyGroups.trend",
    strategyNames: [
      "ema-ribbon",
      "ema-pullback",
      "atr-trailing-trend",
      "sma-crossover",
      "ichimoku-breakout",
      "parabolic-sar",
    ],
  },
  {
    id: "reversal",
    labelKey: "strategyGroups.reversal",
    strategyNames: [
      "bollinger-reversion",
      "rsi-reversal",
      "vwap-reversion",
      "stoch-rsi-reversal",
      "cci-reversal",
      "williams-r-reversal",
      "mfi-reversal",
      "zscore-reversion",
    ],
  },
  {
    id: "breakout",
    labelKey: "strategyGroups.breakout",
    strategyNames: [
      "donchian-breakout",
      "keltner-breakout",
      "bollinger-squeeze-release",
      "momentum-scalping",
    ],
  },
  {
    id: "volume",
    labelKey: "strategyGroups.volume",
    strategyNames: ["obv-trend", "volume-breakout"],
  },
  {
    id: "ensemble",
    labelKey: "strategyGroups.ensemble",
    strategyNames: ["combined-signals"],
  },
];
