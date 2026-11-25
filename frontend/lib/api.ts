/**
 * Central typed API client for the EcoPulse AI FastAPI backend.
 *
 * All backend access flows through this module: base URL resolution, timeouts,
 * error normalisation and a short-lived cache for identical GET requests.
 * Components never hardcode backend URLs.
 */

import type {
  AnalyticsOverviewResponse,
  ConsumptionPatternsResponse,
} from "@/types/analytics";
import type {
  AnomalyDetectionResponse,
  AnomalyHistoryResponse,
  AnomalySummaryResponse,
} from "@/types/anomaly";
import type { ApiErrorBody, Granularity } from "@/types/common";
import type {
  EnergyAggregateResponse,
  EnergyListResponse,
  EnergySummaryResponse,
} from "@/types/energy";
import type {
  ForecastHistoryResponse,
  ForecastRecord,
  ForecastResponse,
  HorizonHours,
} from "@/types/forecast";
import type { HealthResponse } from "@/types/health";
import type { ModelInfo, ModelListResponse } from "@/types/model";

const rawBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

/** Browser-reachable base URL of the FastAPI service, without a trailing slash. */
export const apiBaseUrl = rawBaseUrl.replace(/\/$/, "");

/**
 * Default GET/POST budget. The heavy analytics endpoints (consumption-patterns,
 * overview) take 7-12 s idle and 15-17 s when several widgets refetch at once,
 * so the budget has to sit well above that or slow responses surface as errors
 * even though the backend answers correctly. Connection failures still reject
 * immediately — this only bounds a server that accepted but is not replying.
 */
const DEFAULT_TIMEOUT_MS = 30_000;
/** Recursive 48-hour forecasts take several seconds on the local model. */
const PREDICT_TIMEOUT_MS = 45_000;
/** GET responses are reused briefly so page navigation does not refetch. */
const GET_CACHE_TTL_MS = 20_000;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface TimeRange {
  /** Inclusive start, naive local ISO (`YYYY-MM-DD` or full timestamp). */
  start?: string;
  /** Inclusive end, naive local ISO. */
  end?: string;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Skip the short-lived GET cache (used by explicit refreshes). */
  bypassCache?: boolean;
}

interface CacheEntry {
  storedAt: number;
  value: unknown;
}

const getCache = new Map<string, CacheEntry>();

/**
 * In-flight GETs keyed by URL. Identical concurrent requests (several widgets
 * asking for the same series, StrictMode's double effects) share one network
 * call instead of stampeding the backend.
 */
interface InflightEntry {
  promise: Promise<unknown>;
  controller: AbortController;
  /** Number of live callers; the transport aborts only when it reaches zero. */
  refs: number;
  graceTimer: ReturnType<typeof setTimeout> | null;
  /** Cache generation at creation; refreshes make old entries unjoinable. */
  generation: number;
}

const inflight = new Map<string, InflightEntry>();
let cacheGeneration = 0;
/** Delay before aborting an orphaned request so remounts can re-join it. */
const ABORT_GRACE_MS = 250;

/** Drop every cached GET response (called on manual refresh). */
export function clearApiCache(): void {
  getCache.clear();
  cacheGeneration += 1;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

function rangeParams(range: TimeRange | undefined): { start?: string; end?: string } {
  return { start: range?.start, end: range?.end };
}

async function parseError(response: Response): Promise<ApiError> {
  let code = "unknown_error";
  let message = `Request failed with status ${response.status}`;
  let details: unknown = null;

  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body.error) {
      code = body.error.code;
      message = body.error.message;
      details = body.error.details;
    }
  } catch {
    // Non-JSON error body (proxy/HTML); keep the generic message.
  }

  return new ApiError(response.status, code, message, details);
}

/**
 * Subscribe to an in-flight request. Refcounts the caller's abort signal so
 * the underlying fetch is cancelled only when every subscriber has left.
 */
function attach<T>(entry: InflightEntry, cacheKey: string, signal?: AbortSignal): Promise<T> {
  entry.refs += 1;

  const release = () => {
    entry.refs -= 1;
    if (entry.refs > 0) return;
    if (inflight.get(cacheKey) !== entry || entry.graceTimer !== null) return;
    // Grace period: a StrictMode remount re-subscribes within the same tick.
    entry.graceTimer = setTimeout(() => {
      entry.graceTimer = null;
      if (entry.refs <= 0 && inflight.get(cacheKey) === entry) {
        inflight.delete(cacheKey);
        entry.controller.abort();
      }
    }, ABORT_GRACE_MS);
  };

  signal?.addEventListener("abort", release);

  return entry.promise.then(
    (value) => {
      signal?.removeEventListener("abort", release);
      return value as T;
    },
    (error: unknown) => {
      signal?.removeEventListener("abort", release);
      throw error;
    },
  );
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, timeoutMs, bypassCache } = options;
  const url = `${apiBaseUrl}${path}`;
  const cacheKey = `${method}:${url}`;

  if (method === "GET" && !bypassCache) {
    const hit = getCache.get(cacheKey);
    if (hit && Date.now() - hit.storedAt < GET_CACHE_TTL_MS) {
      return hit.value as T;
    }
  }

  // Join an identical in-flight GET (fresh generation only — a manual
  // refresh must trigger a new request, not reuse a pre-refresh one).
  if (method === "GET") {
    const existing = inflight.get(cacheKey);
    if (existing && existing.generation === cacheGeneration) {
      if (existing.graceTimer !== null) {
        clearTimeout(existing.graceTimer);
        existing.graceTimer = null;
      }
      return attach<T>(existing, cacheKey, signal);
    }
  }

  const controller = new AbortController();
  const generation = cacheGeneration;
  const entry: InflightEntry = {
    promise: Promise.resolve(),
    controller,
    refs: 0,
    graceTimer: null,
    generation,
  };

  const timeout = setTimeout(() => controller.abort(), timeoutMs ?? DEFAULT_TIMEOUT_MS);

  entry.promise = (async (): Promise<unknown> => {
    try {
      let response: Response;
      try {
        response = await fetch(url, {
          method,
          signal: controller.signal,
          cache: "no-store",
          headers: {
            Accept: "application/json",
            ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
          },
          body: body !== undefined ? JSON.stringify(body) : undefined,
        });
      } catch (error) {
        if (signal?.aborted) {
          throw error; // Caller cancelled: propagate for silent teardown.
        }
        const aborted = error instanceof DOMException && error.name === "AbortError";
        throw new ApiError(
          0,
          aborted ? "timeout" : "network_error",
          aborted
            ? `The backend did not respond within ${Math.round((timeoutMs ?? DEFAULT_TIMEOUT_MS) / 1000)}s.`
            : `Cannot reach the EcoPulse AI backend at ${apiBaseUrl}.`,
          null,
        );
      }

      if (!response.ok) {
        throw await parseError(response);
      }

      const value = (await response.json()) as T;

      if (method === "GET" && generation === cacheGeneration) {
        getCache.set(cacheKey, { storedAt: Date.now(), value });
      }

      return value;
    } finally {
      clearTimeout(timeout);
      if (inflight.get(cacheKey) === entry) {
        inflight.delete(cacheKey);
      }
    }
  })();

  if (method === "GET") {
    inflight.set(cacheKey, entry);
  }

  if (method === "GET") {
    return attach<T>(entry, cacheKey, signal);
  }

  // POST: never shared — each caller owns its transport.
  const onPostAbort = () => controller.abort();
  signal?.addEventListener("abort", onPostAbort, { once: true });
  try {
    return (await entry.promise) as T;
  } finally {
    signal?.removeEventListener("abort", onPostAbort);
  }
}

export interface EnergyListParams extends TimeRange {
  limit?: number;
  offset?: number;
  order?: "asc" | "desc";
}

export interface EnergyAggregateParams extends TimeRange {
  limit?: number;
  offset?: number;
  order?: "asc" | "desc";
}

export interface ForecastHistoryParams extends TimeRange {
  model_name?: string;
  forecast_horizon?: HorizonHours;
  limit?: number;
  offset?: number;
}

export interface AnomalyHistoryParams extends TimeRange {
  detection_method?: string;
  is_anomaly?: boolean;
  limit?: number;
  offset?: number;
}

export const api = {
  health: (signal?: AbortSignal) =>
    request<HealthResponse>("/api/v1/health", { signal, bypassCache: true }),

  energy: {
    list: (params: EnergyListParams = {}, signal?: AbortSignal, bypassCache?: boolean) =>
      request<EnergyListResponse>(
        `/api/v1/energy${buildQuery({ ...rangeParams(params), limit: params.limit, offset: params.offset, order: params.order })}`,
        { signal, bypassCache },
      ),

    summary: (params: TimeRange = {}, signal?: AbortSignal, bypassCache?: boolean) =>
      request<EnergySummaryResponse>(
        `/api/v1/energy/summary${buildQuery(rangeParams(params))}`,
        { signal, bypassCache },
      ),

    aggregate: (
      granularity: Granularity,
      params: EnergyAggregateParams = {},
      signal?: AbortSignal,
      bypassCache?: boolean,
    ) =>
      request<EnergyAggregateResponse>(
        `/api/v1/energy/${granularity}${buildQuery({
          ...rangeParams(params),
          limit: params.limit,
          offset: params.offset,
          order: params.order,
        })}`,
        { signal, bypassCache },
      ),
  },

  forecasts: {
    predict: (
      body: { horizon_hours: HorizonHours; base_timestamp?: string },
      signal?: AbortSignal,
    ) =>
      request<ForecastResponse>("/api/v1/forecasts/predict", {
        method: "POST",
        body,
        signal,
        timeoutMs: PREDICT_TIMEOUT_MS,
      }),

    history: (params: ForecastHistoryParams = {}, signal?: AbortSignal, bypassCache?: boolean) =>
      request<ForecastHistoryResponse>(
        `/api/v1/forecasts/history${buildQuery({
          ...rangeParams(params),
          model_name: params.model_name,
          forecast_horizon: params.forecast_horizon,
          limit: params.limit,
          offset: params.offset,
        })}`,
        { signal, bypassCache },
      ),

    latest: (signal?: AbortSignal, bypassCache?: boolean) =>
      request<ForecastRecord>("/api/v1/forecasts/latest", { signal, bypassCache }),
  },

  anomalies: {
    detect: (body: { observation_timestamp: string }, signal?: AbortSignal) =>
      request<AnomalyDetectionResponse>("/api/v1/anomalies/detect", {
        method: "POST",
        body,
        signal,
        timeoutMs: PREDICT_TIMEOUT_MS,
      }),

    history: (params: AnomalyHistoryParams = {}, signal?: AbortSignal, bypassCache?: boolean) =>
      request<AnomalyHistoryResponse>(
        `/api/v1/anomalies${buildQuery({
          ...rangeParams(params),
          detection_method: params.detection_method,
          is_anomaly: params.is_anomaly,
          limit: params.limit,
          offset: params.offset,
        })}`,
        { signal, bypassCache },
      ),

    summary: (signal?: AbortSignal, bypassCache?: boolean) =>
      request<AnomalySummaryResponse>("/api/v1/anomalies/summary", { signal, bypassCache }),
  },

  analytics: {
    overview: (signal?: AbortSignal, bypassCache?: boolean) =>
      request<AnalyticsOverviewResponse>("/api/v1/analytics/overview", {
        signal,
        bypassCache,
      }),

    patterns: (signal?: AbortSignal, bypassCache?: boolean) =>
      request<ConsumptionPatternsResponse>("/api/v1/analytics/consumption-patterns", {
        signal,
        bypassCache,
      }),
  },

  models: {
    list: (signal?: AbortSignal, bypassCache?: boolean) =>
      request<ModelListResponse>("/api/v1/models", { signal, bypassCache }),

    get: (key: ModelInfo["key"], signal?: AbortSignal, bypassCache?: boolean) =>
      request<ModelInfo>(`/api/v1/models/${key}`, { signal, bypassCache }),
  },
};
