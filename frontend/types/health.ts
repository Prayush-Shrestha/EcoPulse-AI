/** Health and readiness contract from GET /api/v1/health. */

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
