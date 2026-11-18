import { siteConfig } from "@/lib/site";

export type CheckStatus = "ok" | "unavailable";
export type HealthStatus = "ok" | "degraded";

export interface HealthCheck {
  status: CheckStatus;
  latency_ms: number | null;
  detail: string | null;
}

export interface HealthResponse {
  status: HealthStatus;
  service: string;
  version: string;
  environment: string;
  timestamp: string;
  checks: Record<string, HealthCheck>;
}

export async function fetchHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(siteConfig.apiHealthUrl, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Health request failed with status ${response.status}`);
  }

  return (await response.json()) as HealthResponse;
}
