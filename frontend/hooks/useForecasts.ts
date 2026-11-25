"use client";

/** Forecast hooks: stored history, latest point and the predict mutation. */

import { useCallback, useMemo, useState } from "react";

import { ApiError, api, type ForecastHistoryParams } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { toApiRange } from "@/lib/utils";
import type {
  ForecastHistoryResponse,
  ForecastRecord,
  ForecastResponse,
  HorizonHours,
} from "@/types/forecast";

import { useApi } from "@/hooks/useApi";
import { useEnergyActuals } from "@/hooks/useEnergyData";

export function useForecastHistory(
  params: Omit<ForecastHistoryParams, "start" | "end"> = {},
): ReturnType<typeof useApi<ForecastHistoryResponse>> {
  const { range, refreshKey } = useApp();
  const apiRange = toApiRange(range);

  return useApi<ForecastHistoryResponse>(
    (signal) => api.forecasts.history({ ...apiRange, ...params }, signal),
    [
      apiRange.start ?? "",
      apiRange.end ?? "",
      params.model_name ?? "",
      params.forecast_horizon ?? "",
      params.limit ?? 100,
      params.offset ?? 0,
      refreshKey,
    ],
  );
}

/** Most recent stored forecast point; `null` when none exist yet (404). */
export function useLatestForecast(): ReturnType<
  typeof useApi<ForecastRecord | null>
> {
  const { refreshKey } = useApp();

  return useApi<ForecastRecord | null>(
    (signal) =>
      api.forecasts.latest(signal).catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }),
    [refreshKey],
  );
}

interface PredictState {
  pending: boolean;
  error: Error | null;
  result: ForecastResponse | null;
}

/** Manual POST /forecasts/predict mutation with explicit lifecycle states. */
export function usePredictForecast() {
  const { refresh } = useApp();
  const [state, setState] = useState<PredictState>({
    pending: false,
    error: null,
    result: null,
  });

  const predict = useCallback(
    async (horizon: HorizonHours, baseTimestamp?: string) => {
      setState((current) => ({ ...current, pending: true, error: null }));
      try {
        const result = await api.forecasts.predict({
          horizon_hours: horizon,
          ...(baseTimestamp ? { base_timestamp: baseTimestamp } : {}),
        });
        setState({ pending: false, error: null, result });
        // Persisted server-side: drop cached history so lists refetch.
        refresh();
        return result;
      } catch (error) {
        setState({
          pending: false,
          error: error instanceof Error ? error : new Error(String(error)),
          result: null,
        });
        return null;
      }
    },
    [refresh],
  );

  const reset = useCallback(() => {
    setState({ pending: false, error: null, result: null });
  }, []);

  return { ...state, predict, reset };
}

/**
 * Stored forecast points joined with actual hourly consumption for the same
 * window. Actuals stay `null` beyond the dataset end, where no measurement
 * exists to compare against.
 */
export function useForecastVsActual(
  params: Omit<ForecastHistoryParams, "start" | "end"> = {},
) {
  const history = useForecastHistory(params);

  const predicted = useMemo(() => {
    const items = [...(history.data?.items ?? [])];
    items.sort((a, b) => a.forecast_timestamp.localeCompare(b.forecast_timestamp));
    return items;
  }, [history.data]);

  const start = predicted[0]?.forecast_timestamp;
  const end = predicted[predicted.length - 1]?.forecast_timestamp;

  const actuals = useEnergyActuals(start, end);

  return {
    predicted,
    actuals: actuals.data?.items ?? [],
    loading: history.loading || (Boolean(start) && actuals.loading),
    error: history.error,
    refresh: history.refresh,
    refreshing: history.refreshing,
    total: history.data?.total ?? 0,
  };
}
