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
    height: 560,
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
      chart.value?.resize(chartEl.value.clientWidth, 560);
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
      color: "#22ab94",
      shape: "arrowUp",
      text: markerLabel("Long", marker.reason),
    };
  }
  if (marker.type === "short_signal") {
    return {
      time,
      position: "aboveBar",
      color: "#f23645",
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
    color: isEntry ? "#2962ff" : "#7c3aed",
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
