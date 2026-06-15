<script setup lang="ts">
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type SeriesMarker,
  type SeriesType,
  type Time,
} from "lightweight-charts";
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import type { Candle, IndicatorDefinition, IndicatorSeries as IndicatorSeriesDefinition, Marker } from "../types";

const props = withDefaults(defineProps<{
  candles: Candle[];
  signals: Marker[];
  indicators?: IndicatorDefinition[];
  showSignals: boolean;
  resetKey: string;
  ariaLabel?: string;
  emptyLabel?: string;
  longSignalLabel?: string;
  shortSignalLabel?: string;
}>(), {
  indicators: () => [],
  ariaLabel: "TradingView live market chart",
  emptyLabel: "No candles returned",
  longSignalLabel: "Long",
  shortSignalLabel: "Short",
});

type IndicatorChartSeries = {
  series: ISeriesApi<"Line", Time> | ISeriesApi<"Histogram", Time>;
  type: IndicatorSeriesDefinition["type"];
};

const chartEl = ref<HTMLElement | null>(null);
const chart = shallowRef<IChartApi | null>(null);
const series = shallowRef<ISeriesApi<"Candlestick"> | null>(null);
const markerApi = shallowRef<ISeriesMarkersPluginApi<Time> | null>(null);
const indicatorSeries = new Map<string, IndicatorChartSeries>();
const DEFAULT_CHART_HEIGHT = 560;
let resizeObserver: ResizeObserver | null = null;
let shouldFitContent = true;

const visibleMarkers = computed(() =>
  props.showSignals ? props.signals.map(signalMarker) : [],
);

watch(() => props.resetKey, () => {
  shouldFitContent = true;
});

watch(
  () => [props.candles, visibleMarkers.value, props.indicators],
  async () => {
    await nextTick();
    renderChart();
  },
  { deep: true, immediate: true },
);

onBeforeUnmount(() => {
  clearIndicatorSeries();
  resizeObserver?.disconnect();
  chart.value?.remove();
});

function renderChart() {
  if (!chartEl.value || props.candles.length === 0) {
    return;
  }
  ensureChart();
  const candleData = props.candles.map(toCandleData);
  const timeScale = chart.value?.timeScale();
  const visibleRange = shouldFitContent ? null : timeScale?.getVisibleLogicalRange();
  series.value?.setData(candleData);
  syncIndicatorSeries();
  markerApi.value?.setMarkers(
    visibleMarkers.value
      .filter((marker): marker is SeriesMarker<Time> => marker !== null)
      .sort((left, right) => Number(left.time) - Number(right.time)),
  );
  if (shouldFitContent) {
    timeScale?.fitContent();
    shouldFitContent = false;
  } else if (visibleRange) {
    timeScale?.setVisibleLogicalRange(visibleRange);
  }
}

function ensureChart() {
  if (!chartEl.value || chart.value) {
    return;
  }
  chart.value = createChart(chartEl.value, {
    height: chartHeight(),
    width: chartEl.value.clientWidth || 900,
    layout: {
      background: { type: ColorType.Solid, color: "#131722" },
      textColor: "#d1d4dc",
    },
    grid: {
      vertLines: { color: "#2a2e39" },
      horzLines: { color: "#2a2e39" },
    },
    rightPriceScale: {
      borderColor: "#2a2e39",
    },
    timeScale: {
      borderColor: "#2a2e39",
      timeVisible: true,
      secondsVisible: false,
    },
  });
  series.value = chart.value.addSeries(CandlestickSeries, {
    upColor: "#22ab94",
    downColor: "#f23645",
    borderVisible: false,
    wickUpColor: "#22ab94",
    wickDownColor: "#f23645",
  });
  markerApi.value = createSeriesMarkers(series.value, []);
  resizeObserver = new ResizeObserver(() => {
    if (chartEl.value) {
      chart.value?.resize(chartEl.value.clientWidth, chartHeight());
    }
  });
  resizeObserver.observe(chartEl.value);
}

function chartHeight(): number {
  return chartEl.value?.clientHeight || DEFAULT_CHART_HEIGHT;
}

function toCandleData(candle: Candle): CandlestickData {
  return {
    time: toChartTime(candle.time),
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  };
}

function syncIndicatorSeries() {
  if (!chart.value) {
    return;
  }
  const visibleSeries = new Map<string, {
    indicator: IndicatorDefinition;
    series: IndicatorSeriesDefinition;
  }>();
  for (const indicator of props.indicators) {
    for (const indicatorSeriesItem of indicator.series) {
      visibleSeries.set(seriesKey(indicator, indicatorSeriesItem), {
        indicator,
        series: indicatorSeriesItem,
      });
    }
  }

  for (const [key, entry] of indicatorSeries.entries()) {
    if (!visibleSeries.has(key)) {
      chart.value.removeSeries(entry.series as unknown as ISeriesApi<SeriesType, Time>);
      indicatorSeries.delete(key);
    }
  }

  for (const [key, item] of visibleSeries.entries()) {
    const entry = indicatorSeries.get(key) ?? createIndicatorSeries(item.indicator, item.series);
    indicatorSeries.set(key, entry);
    if (entry.type === "histogram") {
      (entry.series as ISeriesApi<"Histogram", Time>).setData(toHistogramData(item.series));
    } else {
      (entry.series as ISeriesApi<"Line", Time>).setData(toLineData(item.series));
    }
  }
  resizeIndicatorPanes();
}

function createIndicatorSeries(
  indicator: IndicatorDefinition,
  indicatorSeriesItem: IndicatorSeriesDefinition,
): IndicatorChartSeries {
  if (!chart.value) {
    throw new Error("chart is not initialized");
  }
  const paneIndex = paneIndexForIndicator(indicator);
  if (indicatorSeriesItem.type === "histogram") {
    return {
      type: "histogram",
      series: chart.value.addSeries(HistogramSeries, {
        color: indicatorSeriesItem.color,
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat: { type: "volume" },
      }, paneIndex),
    };
  }
  return {
    type: "line",
    series: chart.value.addSeries(LineSeries, {
      color: indicatorSeriesItem.color,
      lineWidth: indicator.pane === "price" ? 1 : 2,
      lastValueVisible: false,
      priceLineVisible: false,
    }, paneIndex),
  };
}

function clearIndicatorSeries() {
  if (!chart.value) {
    indicatorSeries.clear();
    return;
  }
  for (const entry of indicatorSeries.values()) {
    chart.value.removeSeries(entry.series as unknown as ISeriesApi<SeriesType, Time>);
  }
  indicatorSeries.clear();
}

function resizeIndicatorPanes() {
  const panes = chart.value?.panes() ?? [];
  panes[0]?.setStretchFactor(props.indicators.some((indicator) => indicator.pane !== "price") ? 4 : 1);
  panes[1]?.setStretchFactor(1.15);
  panes[2]?.setStretchFactor(1.1);
  panes[3]?.setStretchFactor(1.1);
  panes[4]?.setStretchFactor(1.05);
}

function paneIndexForIndicator(indicator: IndicatorDefinition): number {
  if (indicator.pane === "price") {
    return 0;
  }
  if (indicator.id === "volume") {
    return 1;
  }
  if (indicator.id === "rsi" || indicator.id === "stoch-rsi") {
    return 2;
  }
  if (indicator.id === "macd") {
    return 3;
  }
  return 4;
}

function seriesKey(
  indicator: IndicatorDefinition,
  indicatorSeriesItem: IndicatorSeriesDefinition,
): string {
  return `${indicator.id}:${indicatorSeriesItem.id}`;
}

function toLineData(indicatorSeriesItem: IndicatorSeriesDefinition): LineData[] {
  return indicatorSeriesItem.points.map((point) => ({
    time: toChartTime(point.time),
    value: Number(point.value),
  }));
}

function toHistogramData(indicatorSeriesItem: IndicatorSeriesDefinition): HistogramData[] {
  return indicatorSeriesItem.points.map((point) => ({
    time: toChartTime(point.time),
    value: Number(point.value),
    color: indicatorSeriesItem.color,
  }));
}

function signalMarker(marker: Marker): SeriesMarker<Time> | null {
  const time = toChartTime(marker.time);
  if (marker.type === "long_signal") {
    return {
      time,
      position: "belowBar",
      color: "#22ab94",
      shape: "arrowUp",
      text: markerLabel(props.longSignalLabel, marker.reason),
    };
  }
  if (marker.type === "short_signal") {
    return {
      time,
      position: "aboveBar",
      color: "#f23645",
      shape: "arrowDown",
      text: markerLabel(props.shortSignalLabel, marker.reason),
    };
  }
  return null;
}

function markerLabel(prefix: string, reason: string): string {
  return reason ? `${prefix} ${reason.slice(0, 18)}` : prefix;
}

function toChartTime(value: number): Time {
  const seconds = Math.floor(value > 1_000_000_000_000 ? value / 1000 : value);
  return seconds as Time;
}
</script>

<template>
  <div v-if="candles.length" ref="chartEl" class="tv-chart" :aria-label="ariaLabel" />
  <div v-else class="empty">{{ emptyLabel }}</div>
</template>
