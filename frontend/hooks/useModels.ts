"use client";

/** Loaded Phase 4 model metadata. */

import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import type { ModelListResponse } from "@/types/model";

import { useApi } from "@/hooks/useApi";

export function useModels(): ReturnType<typeof useApi<ModelListResponse>> {
  const { refreshKey } = useApp();

  return useApi<ModelListResponse>((signal) => api.models.list(signal), [refreshKey]);
}
