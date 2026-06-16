import type { Marker } from "./types";
import type { SelectOption } from "./liveConfig";

export function normalizeSearchText(value: string | number): string {
  return String(value).trim().toLowerCase();
}

export function optionMatchesSearch(option: SelectOption, query: string): boolean {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) {
    return true;
  }
  return normalizeSearchText(`${option.label} ${option.value}`).includes(normalizedQuery);
}

export function groupSignalsByConsensus(
  signals: Marker[],
  minimumConfirmations: number,
): Marker[] {
  const minimum = Math.max(1, Math.floor(Number(minimumConfirmations) || 1));
  const groups = new Map<string, Marker[]>();
  for (const signal of signals) {
    const key = `${signal.time}:${signal.type}`;
    groups.set(key, [...(groups.get(key) ?? []), signal]);
  }
  return [...groups.values()]
    .filter((group) => group.length >= minimum)
    .map((group) => consensusMarkerFromGroup(group))
    .sort((left, right) => Number(left.time) - Number(right.time));
}

export function limitRecentSignals(signals: Marker[], limit: number): Marker[] {
  const normalizedLimit = Math.max(0, Math.floor(Number(limit) || 0));
  if (!normalizedLimit || signals.length <= normalizedLimit) {
    return signals;
  }
  return signals.slice(-normalizedLimit);
}

function consensusMarkerFromGroup(group: Marker[]): Marker {
  const first = group[0];
  return {
    time: first.time,
    price: first.price,
    type: first.type,
    reason: formatConsensusReason(group),
  };
}

function formatConsensusReason(group: Marker[]): string {
  const strategyNames = distinctStrategyNames(group).join(", ");
  return strategyNames ? `${group.length}: ${strategyNames}` : String(group.length);
}

function distinctStrategyNames(group: Marker[]): string[] {
  return [
    ...new Set(
      group
        .map((marker) => {
          const separator = marker.reason.indexOf(":");
          return separator > 0 ? marker.reason.slice(0, separator) : "";
        })
        .filter(Boolean),
    ),
  ];
}
