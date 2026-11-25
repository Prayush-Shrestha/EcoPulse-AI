"use client";

/** Analytics endpoints: overview and consumption patterns. */

import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import type { AnalyticsOverviewResponse, ConsumptionPatternsResponse } from "@/types/analytics";

import { useApi } from "@/hooks/useApi";

export function useAnalyticsOverview(): ReturnType<typeof useApi<AnalyticsOverviewResponse>> {
  const { refreshKey } = useApp();

  return useApi<AnalyticsOverviewResponse>(
    (signal) => api.analytics.overview(signal),
    [refreshKey],
  );
}

export function useConsumptionPatterns(): ReturnType<
  typeof useApi<ConsumptionPatternsResponse>
> {
  const { refreshKey } = useApp();

  return useApi<ConsumptionPatternsResponse>(
    (signal) => api.analytics.patterns(signal),
    [refreshKey],
  );
}
