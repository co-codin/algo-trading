<script setup lang="ts">
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import type { Candle, Marker } from "../types";

const props = defineProps<{
  candles: Candle[];
  signals: Marker[];
  paperMarkers: Marker[];
  showSignals: boolean;
  showPaper: boolean;
}>();

const chartEl = ref<HTMLElement | null>(null);
const chart = shallowRef<IChartApi | null>(null);
const series = shallowRef<ISeriesApi<"Candlestick"> | null>(null);
const markerApi = shallowRef<ISeriesMarkersPluginApi<Time> | null>(null);
let resizeObserver: ResizeObserver | null = null;

const visibleMarkers = computed(() => [
  ...(props.showSignals ? props.signals.map(signalMarker) : []),
  ...(props.showPaper ? props.paperMarkers.map(paperMarker) : []),
]);

watch(
  () => [props.candles, visibleMarkers.value],
  async () => {
    await nextTick();
    renderChart();
  },
  { deep: true, immediate: true },
);

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  chart.value?.remove();
});

function renderChart() {
  if (!chartEl.value || props.candles.length === 0) {
    return;
  }
  ensureChart();
  const candleData = props.candles.map(toCandleData);
  series.value?.setData(candleData);
  markerApi.value?.setMarkers(
    visibleMarkers.value
      .filter((marker): marker is SeriesMarker<Time> => marker !== null)
      .sort((left, right) => Number(left.time) - Number(right.time)),
  );
  chart.value?.timeScale().fitContent();
}

function ensureChart() {
  if (!chartEl.value || chart.value) {
    return;
  }
  chart.value = createChart(chartEl.value, {
    height: 460,
    width: chartEl.value.clientWidth || 900,
    layout: {
      background: { type: ColorType.Solid, color: "#fbfcfc" },
      textColor: "#5f6965",
    },
    grid: {
      vertLines: { color: "#e2e8e5" },
      horzLines: { color: "#e2e8e5" },
    },
    rightPriceScale: {
      borderColor: "#d9dfdd",
    },
    timeScale: {
      borderColor: "#d9dfdd",
      timeVisible: true,
      secondsVisible: false,
    },
  });
  series.value = chart.value.addSeries(CandlestickSeries, {
    upColor: "#2f8f5b",
    downColor: "#b35c2e",
    borderVisible: false,
    wickUpColor: "#2f8f5b",
    wickDownColor: "#b35c2e",
  });
  markerApi.value = createSeriesMarkers(series.value, []);
  resizeObserver = new ResizeObserver(() => {
    if (chartEl.value) {
      chart.value?.resize(chartEl.value.clientWidth, 460);
    }
  });
  resizeObserver.observe(chartEl.value);
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

function signalMarker(marker: Marker): SeriesMarker<Time> | null {
  const time = toChartTime(marker.time);
  if (marker.type === "long_signal") {
    return {
      time,
      position: "belowBar",
      color: "#2f8f5b",
      shape: "arrowUp",
      text: markerLabel("Long", marker.reason),
    };
  }
  if (marker.type === "short_signal") {
    return {
      time,
      position: "aboveBar",
      color: "#b35c2e",
      shape: "arrowDown",
      text: markerLabel("Short", marker.reason),
    };
  }
  return null;
}

function paperMarker(marker: Marker): SeriesMarker<Time> | null {
  const isShort = marker.type.includes("short");
  const isEntry = marker.type.startsWith("paper_entry");
  return {
    time: toChartTime(marker.time),
    position: isShort ? "aboveBar" : "belowBar",
    color: isEntry ? "#246aa8" : "#6d5cae",
    shape: isEntry ? (isShort ? "arrowDown" : "arrowUp") : "square",
    text: markerLabel(isEntry ? "Paper" : "Exit", marker.reason),
  };
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
  <div v-if="candles.length" ref="chartEl" class="tv-chart" aria-label="TradingView live market chart" />
  <div v-else class="empty">No candles returned</div>
</template>
