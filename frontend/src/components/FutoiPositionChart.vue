<script setup lang="ts">
import {
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from "lightweight-charts";
import { nextTick, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import type { FutoiChartPoint } from "../types";

type FutoiChartLabels = {
  aria: string;
  empty: string;
  net: string;
  long: string;
  short: string;
  openInterest: string;
};

const props = defineProps<{
  points: FutoiChartPoint[];
  labels: FutoiChartLabels;
}>();

const chartEl = ref<HTMLElement | null>(null);
const chart = shallowRef<IChartApi | null>(null);
const netSeries = shallowRef<ISeriesApi<"Line", Time> | null>(null);
const longSeries = shallowRef<ISeriesApi<"Line", Time> | null>(null);
const shortSeries = shallowRef<ISeriesApi<"Line", Time> | null>(null);
const openInterestSeries = shallowRef<ISeriesApi<"Line", Time> | null>(null);
const DEFAULT_CHART_HEIGHT = 360;
let resizeObserver: ResizeObserver | null = null;

watch(
  () => props.points,
  async () => {
    await nextTick();
    renderChart();
  },
  { deep: true, immediate: true },
);

watch(
  () => props.labels,
  () => {
    updateSeriesOptions();
  },
  { deep: true },
);

onBeforeUnmount(() => {
  removeChart();
});

function renderChart() {
  if (props.points.length === 0) {
    removeChart();
    return;
  }
  if (!chartEl.value) {
    return;
  }
  ensureChart();
  netSeries.value?.setData(toLineData("net_position"));
  longSeries.value?.setData(toLineData("long_position"));
  shortSeries.value?.setData(toLineData("short_position"));
  openInterestSeries.value?.setData(toLineData("open_interest"));
  chart.value?.timeScale().fitContent();
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
  netSeries.value = chart.value.addSeries(LineSeries, {
    color: "#2962ff",
    lineWidth: 2,
    title: props.labels.net,
  });
  longSeries.value = chart.value.addSeries(LineSeries, {
    color: "#22ab94",
    lineWidth: 2,
    title: props.labels.long,
  });
  shortSeries.value = chart.value.addSeries(LineSeries, {
    color: "#f23645",
    lineWidth: 2,
    title: props.labels.short,
  });
  openInterestSeries.value = chart.value.addSeries(LineSeries, {
    color: "#f59e0b",
    lineWidth: 1,
    title: props.labels.openInterest,
  });
  resizeObserver = new ResizeObserver(() => {
    if (chartEl.value) {
      chart.value?.resize(chartEl.value.clientWidth, chartHeight());
    }
  });
  resizeObserver.observe(chartEl.value);
}

function updateSeriesOptions() {
  netSeries.value?.applyOptions({ title: props.labels.net });
  longSeries.value?.applyOptions({ title: props.labels.long });
  shortSeries.value?.applyOptions({ title: props.labels.short });
  openInterestSeries.value?.applyOptions({ title: props.labels.openInterest });
}

function toLineData(field: keyof Omit<FutoiChartPoint, "time">): LineData[] {
  return props.points.map((point) => ({
    time: point.time as Time,
    value: Number(point[field]),
  }));
}

function chartHeight(): number {
  return chartEl.value?.clientHeight || DEFAULT_CHART_HEIGHT;
}

function removeChart() {
  resizeObserver?.disconnect();
  resizeObserver = null;
  netSeries.value = null;
  longSeries.value = null;
  shortSeries.value = null;
  openInterestSeries.value = null;
  chart.value?.remove();
  chart.value = null;
}
</script>

<template>
  <div v-if="points.length" ref="chartEl" class="futoi-position-chart" :aria-label="labels.aria" />
  <div v-else class="empty">{{ labels.empty }}</div>
</template>
