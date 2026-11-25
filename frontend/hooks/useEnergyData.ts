"use client";

/** Energy data hooks: summary, chart series and the readings explorer. */

import { useMemo } from "react";

import { api, type EnergyAggregateParams } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { toApiRange } from "@/lib/utils";
import type {
  EnergyAggregateResponse,
  EnergyListResponse,
  EnergySummaryResponse,
} from "@/types/energy";
import type { Granularity } from "@/types/common";

import { useApi } from "@/hooks/useApi";

/** Points requested when the header has no explicit range (most recent first). */
const DEFAULT_WINDOW: Record<Granularity, number> = {
  hourly: 336, // two weeks of hours
  daily: 120, // four months of days
  monthly: 48, // four years of months
};

const MAX_RANGE_POINTS = 5_000; // backend limit for aggregate pages

export function useEnergySummary(): UseApiSummary {
  const { range, refreshKey } = useApp();
  const apiRange = useMemo(() => toApiRange(range), [range]);

  return useApi<EnergySummaryResponse>(
    (signal) => api.energy.summary(apiRange, signal),
    [apiRange.start ?? "", apiRange.end ?? "", refreshKey],
  );
}

type UseApiSummary = ReturnType<typeof useApi<EnergySummaryResponse>>;

export interface EnergySeries {
  response: EnergyAggregateResponse | null;
  /** Chart points ordered oldest → newest. */
  items: EnergyAggregateResponse["items"];
  /** True when the backend total exceeds the fetched page. */
  truncated: boolean;
}

/**
 * Aggregated series for the consumption charts.
 * Without a header range the most recent window is fetched (descending) and
 * reversed for plotting; with a range the full window is fetched ascending.
 */
export function useEnergySeries(granularity: Granularity): ReturnType<typeof useApi<EnergyAggregateResponse>> & {
  series: EnergySeries;
} {
  const { range, refreshKey } = useApp();
  const hasRange = Boolean(range.start || range.end);
  const params: EnergyAggregateParams = hasRange
    ? { ...toApiRange(range), limit: MAX_RANGE_POINTS, order: "asc" }
    : { limit: DEFAULT_WINDOW[granularity], order: "desc" };

  const result = useApi<EnergyAggregateResponse>(
    (signal) => api.energy.aggregate(granularity, params, signal),
    [
      granularity,
      hasRange ? "range" : "default",
      params.start ?? "",
      params.end ?? "",
      params.limit,
      refreshKey,
    ],
  );

  const raw = useMemo(() => result.data?.items ?? [], [result.data]);
  const items = useMemo(
    () => (params.order === "desc" ? [...raw].reverse() : raw),
    [raw, params.order],
  );

  return {
    ...result,
    series: {
      response: result.data,
      items,
      truncated: (result.data?.total ?? 0) > items.length && items.length > 0,
    },
  };
}

export function useEnergyReadings(
  page: { limit: number; offset?: number; order: "asc" | "desc" },
): ReturnType<typeof useApi<EnergyListResponse>> {
  const { range, refreshKey } = useApp();
  const apiRange = useMemo(() => toApiRange(range), [range]);

  return useApi<EnergyListResponse>(
    (signal) =>
      api.energy.list({ ...apiRange, ...page, offset: page.offset ?? 0 }, signal),
    [
      apiRange.start ?? "",
      apiRange.end ?? "",
      page.limit,
      page.offset ?? 0,
      page.order,
      refreshKey,
    ],
  );
}

/**
 * Aggregates for an explicit window (used to plot actuals next to a
 * forecast). Resolves `null` until both bounds are known, so no request
 * is fired with a partial range.
 */
export function useEnergyActuals(
  start?: string,
  end?: string,
  granularity: Granularity = "hourly",
): ReturnType<typeof useApi<EnergyAggregateResponse | null>> {
  const { refreshKey } = useApp();

  return useApi<EnergyAggregateResponse | null>(
    (signal) => {
      if (!start || !end) return Promise.resolve(null);
      return api.energy.aggregate(granularity, { start, end, limit: 2_000, order: "asc" }, signal);
    },
    [start ?? "", end ?? "", granularity, refreshKey],
  );
}
