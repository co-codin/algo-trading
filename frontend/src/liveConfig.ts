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

export const liveSymbolOptions = [
  { value: "BTCUSDT", label: "BTCUSDT" },
  { value: "ETHUSDT", label: "ETHUSDT" },
] satisfies SelectOption[];

export const mag7StockSymbolOptions = [
  { value: "AAPL", label: "AAPL · Apple" },
  { value: "AMZN", label: "AMZN · Amazon" },
  { value: "GOOGL", label: "GOOGL · Alphabet" },
  { value: "META", label: "META · Meta" },
  { value: "MSFT", label: "MSFT · Microsoft" },
  { value: "NVDA", label: "NVDA · NVIDIA" },
  { value: "TSLA", label: "TSLA · Tesla" },
] satisfies SelectOption[];

export const hongKongStockSymbolOptions = [
  { value: "0700.HK", label: "0700.HK · Tencent" },
  { value: "9988.HK", label: "9988.HK · Alibaba" },
  { value: "9888.HK", label: "9888.HK · Baidu" },
  { value: "3690.HK", label: "3690.HK · Meituan" },
  { value: "9618.HK", label: "9618.HK · JD.com" },
  { value: "9999.HK", label: "9999.HK · NetEase" },
  { value: "1810.HK", label: "1810.HK · Xiaomi" },
  { value: "1024.HK", label: "1024.HK · Kuaishou" },
  { value: "0968.HK", label: "0968.HK · Xpeng" },
  { value: "2015.HK", label: "2015.HK · Li Auto" },
  { value: "1211.HK", label: "1211.HK · BYD" },
  { value: "2318.HK", label: "2318.HK · Ping An" },
  { value: "0939.HK", label: "0939.HK · China Construction Bank" },
  { value: "1398.HK", label: "1398.HK · ICBC" },
  { value: "0388.HK", label: "0388.HK · HKEX" },
  { value: "1299.HK", label: "1299.HK · AIA" },
  { value: "0005.HK", label: "0005.HK · HSBC" },
  { value: "0941.HK", label: "0941.HK · China Mobile" },
  { value: "0883.HK", label: "0883.HK · CNOOC" },
  { value: "2628.HK", label: "2628.HK · China Life" },
] satisfies SelectOption[];

export const moexBluechipSymbolOptions = [
  { value: "AFKS", label: "AFKS" },
  { value: "AFLT", label: "AFLT" },
  { value: "ALRS", label: "ALRS" },
  { value: "ASTR", label: "ASTR" },
  { value: "BANEP", label: "BANEP" },
  { value: "BELU", label: "BELU" },
  { value: "BSPB", label: "BSPB" },
  { value: "CBOM", label: "CBOM" },
  { value: "CHMF", label: "CHMF" },
  { value: "CNRU", label: "CNRU" },
  { value: "DATA", label: "DATA" },
  { value: "DIAS", label: "DIAS" },
  { value: "DOMRF", label: "DOMRF" },
  { value: "ENPG", label: "ENPG" },
  { value: "ETLN", label: "ETLN" },
  { value: "EUTR", label: "EUTR" },
  { value: "FEES", label: "FEES" },
  { value: "FESH", label: "FESH" },
  { value: "FIXR", label: "FIXR" },
  { value: "FLOT", label: "FLOT" },
  { value: "GAZP", label: "GAZP" },
  { value: "GMKN", label: "GMKN" },
  { value: "HEAD", label: "HEAD" },
  { value: "IRAO", label: "IRAO" },
  { value: "IVAT", label: "IVAT" },
  { value: "LENT", label: "LENT" },
  { value: "LKOH", label: "LKOH" },
  { value: "LSNGP", label: "LSNGP" },
  { value: "LSRG", label: "LSRG" },
  { value: "MAGN", label: "MAGN" },
  { value: "MGNT", label: "MGNT" },
  { value: "MOEX", label: "MOEX" },
  { value: "MRKC", label: "MRKC" },
  { value: "MRKV", label: "MRKV" },
  { value: "MSNG", label: "MSNG" },
  { value: "MTLR", label: "MTLR" },
  { value: "MTLRP", label: "MTLRP" },
  { value: "MTSS", label: "MTSS" },
  { value: "MVID", label: "MVID" },
  { value: "NLMK", label: "NLMK" },
  { value: "NMTP", label: "NMTP" },
  { value: "NVTK", label: "NVTK" },
  { value: "OZON", label: "OZON" },
  { value: "PHOR", label: "PHOR" },
  { value: "PIKK", label: "PIKK" },
  { value: "PLZL", label: "PLZL" },
  { value: "POSI", label: "POSI" },
  { value: "RAGR", label: "RAGR" },
  { value: "RASP", label: "RASP" },
  { value: "RENI", label: "RENI" },
  { value: "RNFT", label: "RNFT" },
  { value: "ROSN", label: "ROSN" },
  { value: "RTKM", label: "RTKM" },
  { value: "RUAL", label: "RUAL" },
  { value: "SBER", label: "SBER" },
  { value: "SBERP", label: "SBERP" },
  { value: "SELG", label: "SELG" },
  { value: "SFIN", label: "SFIN" },
  { value: "SGZH", label: "SGZH" },
  { value: "SIBN", label: "SIBN" },
  { value: "SMLT", label: "SMLT" },
  { value: "SNGS", label: "SNGS" },
  { value: "SNGSP", label: "SNGSP" },
  { value: "SPBE", label: "SPBE" },
  { value: "SVCB", label: "SVCB" },
  { value: "T", label: "T" },
  { value: "TATN", label: "TATN" },
  { value: "TATNP", label: "TATNP" },
  { value: "TRMK", label: "TRMK" },
  { value: "TRNFP", label: "TRNFP" },
  { value: "UGLD", label: "UGLD" },
  { value: "UPRO", label: "UPRO" },
  { value: "VKCO", label: "VKCO" },
  { value: "VTBR", label: "VTBR" },
  { value: "WUSH", label: "WUSH" },
  { value: "X5", label: "X5" },
  { value: "YDEX", label: "YDEX" },
] satisfies SelectOption[];

export const moexIndexSymbolOptions = [
  { value: "IMOEX", label: "IMOEX · MOEX Russia Index" },
  { value: "RTSI", label: "RTSI · RTS Index" },
] satisfies SelectOption[];

export const moexFuturesSymbolOptions = [
  { value: "IMOEXF", label: "IMOEXF · IMOEX Futures" },
  { value: "MXM6", label: "MXM6 · MOEX Index Futures" },
  { value: "MXU6", label: "MXU6 · MOEX Index Futures" },
  { value: "MXZ6", label: "MXZ6 · MOEX Index Futures" },
  { value: "RIM6", label: "RIM6 · RTS Index Futures" },
  { value: "RIU6", label: "RIU6 · RTS Index Futures" },
  { value: "RIZ6", label: "RIZ6 · RTS Index Futures" },
] satisfies SelectOption[];

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
