"use client";

/** Anomaly hooks: stored detections, summary and the detect mutation. */

import { useCallback, useState } from "react";

import { api, type AnomalyHistoryParams } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { toApiRange } from "@/lib/utils";
import type {
  AnomalyDetectionResponse,
  AnomalyHistoryResponse,
  AnomalySummaryResponse,
} from "@/types/anomaly";

import { useApi } from "@/hooks/useApi";

export function useAnomalyHistory(
  params: Omit<AnomalyHistoryParams, "start" | "end"> = {},
): ReturnType<typeof useApi<AnomalyHistoryResponse>> {
  const { range, refreshKey } = useApp();
  const apiRange = toApiRange(range);

  return useApi<AnomalyHistoryResponse>(
    (signal) => api.anomalies.history({ ...apiRange, ...params }, signal),
    [
      apiRange.start ?? "",
      apiRange.end ?? "",
      params.detection_method ?? "",
      params.is_anomaly === undefined ? "" : String(params.is_anomaly),
      params.limit ?? 100,
      params.offset ?? 0,
      refreshKey,
    ],
  );
}

export function useAnomalySummary(): ReturnType<typeof useApi<AnomalySummaryResponse>> {
  const { refreshKey } = useApp();

  return useApi<AnomalySummaryResponse>(
    (signal) => api.anomalies.summary(signal),
    [refreshKey],
  );
}

interface DetectState {
  pending: boolean;
  error: Error | null;
  result: AnomalyDetectionResponse | null;
}

/** Manual POST /anomalies/detect mutation. */
export function useDetectAnomaly() {
  const { refresh } = useApp();
  const [state, setState] = useState<DetectState>({
    pending: false,
    error: null,
    result: null,
  });

  const detect = useCallback(
    async (observationTimestamp: string) => {
      setState((current) => ({ ...current, pending: true, error: null }));
      try {
        const result = await api.anomalies.detect({
          observation_timestamp: observationTimestamp,
        });
        setState({ pending: false, error: null, result });
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

  return { ...state, detect, reset };
}
