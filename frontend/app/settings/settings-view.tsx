"use client";

/** Settings: connection, health, model and dataset information (no secrets). */

import type { ReactNode } from "react";
import { Activity, BookOpen, Database, Layers, Palette, Server } from "lucide-react";

import { SystemStatus } from "@/components/dashboard/SystemStatus";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useAnalyticsOverview } from "@/hooks/useAnalytics";
import { useModels } from "@/hooks/useModels";
import { useHealth } from "@/hooks/useHealth";
import { apiBaseUrl } from "@/lib/api";
import { formatCount, formatDateTime, formatKwh } from "@/lib/formatters";
import { siteConfig } from "@/lib/site";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <dt className="shrink-0 text-xs text-muted">{label}</dt>
      <dd className="min-w-0 truncate text-right text-xs text-ink">{children}</dd>
    </div>
  );
}

function SectionIcon({ icon: Icon }: { icon: typeof Activity }) {
  return (
    <span
      className="grid size-8 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary"
      aria-hidden
    >
      <Icon className="size-4" />
    </span>
  );
}

export function SettingsView() {
  const health = useHealth(30_000);
  const models = useModels();
  const overview = useAnalyticsOverview();

  const energy = overview.data?.energy;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* API connection */}
      <Card
        title="API connection"
        subtitle="FastAPI backend consumed by this dashboard"
        action={<SectionIcon icon={Server} />}
      >
        <dl className="divide-y divide-line/50">
          <Row label="Base URL">
            <span className="font-mono">{apiBaseUrl}</span>
          </Row>
          <Row label="Health endpoint">
            <span className="font-mono">{apiBaseUrl}/api/v1/health</span>
          </Row>
          <Row label="API docs">
            <a
              href={`${apiBaseUrl}/docs`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              <BookOpen className="size-3" aria-hidden />
              Open /docs
            </a>
          </Row>
          <Row label="Status">
            {health.error ? (
              <Badge tone="danger" dot>
                unreachable
              </Badge>
            ) : health.data ? (
              <Badge tone={health.data.status === "ok" ? "ok" : "warning"} dot>
                {health.data.status}
              </Badge>
            ) : (
              <Badge tone="neutral">checking…</Badge>
            )}
          </Row>
          <Row label="Last checked">
            {health.checkedAt
              ? health.checkedAt.toLocaleTimeString("en-GB")
              : "—"}
          </Row>
          <Row label="Configuration">
            <span className="text-muted">NEXT_PUBLIC_API_BASE_URL</span>
          </Row>
        </dl>
        <p className="mt-3 rounded-lg border border-line/70 bg-canvas/60 px-3.5 py-2.5 text-[11px] leading-5 text-muted">
          Only the public base URL is exposed to the browser. No API keys, tokens or database
          credentials ship in <span className="font-mono text-ink">NEXT_PUBLIC_*</span> variables.
        </p>
      </Card>

      {/* Backend health */}
      <div className="min-w-0">
        <SystemStatus />
      </div>

      {/* Models */}
      <Card
        title="Model status"
        subtitle="Phase 4 artefacts loaded by the backend"
        action={<SectionIcon icon={Layers} />}
      >
        {models.loading && !models.data ? (
          <ChartSkeleton height={160} />
        ) : models.error && !models.data ? (
          <ErrorState error={models.error} onRetry={models.refresh} />
        ) : !models.data || models.data.models.length === 0 ? (
          <EmptyState
            title="No models reported"
            description="The backend returned no model metadata."
            className="min-h-0 py-6"
          />
        ) : (
          <ul className="space-y-3">
            {models.data.models.map((model) => (
              <li key={model.key} className="rounded-lg border border-line/70 px-3.5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="min-w-0 truncate text-xs font-medium text-ink">{model.name}</p>
                  <Badge tone={model.status === "loaded" ? "ok" : "warning"}>
                    {model.status}
                  </Badge>
                </div>
                <dl className="mt-2 space-y-1 text-[11px] text-muted">
                  <div className="flex justify-between gap-3">
                    <dt>Key</dt>
                    <dd className="font-mono text-ink/90">{model.key}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>Version</dt>
                    <dd className="font-mono text-ink/90">{model.version ?? "—"}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>Type</dt>
                    <dd className="font-mono text-ink/90">{model.model_type ?? "—"}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>Trained</dt>
                    <dd className="font-mono text-ink/90">
                      {model.trained_at_utc ? formatDateTime(model.trained_at_utc) : "—"}
                    </dd>
                  </div>
                  {model.metrics
                    ? Object.entries(model.metrics).map(([name, value]) => (
                        <div key={name} className="flex justify-between gap-3">
                          <dt className="uppercase">{name}</dt>
                          <dd className="font-mono text-ink/90">{value.toFixed(4)}</dd>
                        </div>
                      ))
                    : null}
                  {model.threshold !== null ? (
                    <div className="flex justify-between gap-3">
                      <dt>Anomaly threshold</dt>
                      <dd className="font-mono text-ink/90">{model.threshold.toFixed(4)}</dd>
                    </div>
                  ) : null}
                </dl>
                {model.detail ? (
                  <p className="mt-2 text-[10px] leading-4 text-muted/80">{model.detail}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {models.data?.label_status ? (
          <p className="mt-3 text-[10px] text-muted/80">{models.data.label_status}</p>
        ) : null}
      </Card>

      {/* Dataset */}
      <Card
        title="Dataset"
        subtitle="Stored in PostgreSQL through the Phase 3 ETL"
        action={<SectionIcon icon={Database} />}
      >
        {overview.loading && !overview.data ? (
          <ChartSkeleton height={160} />
        ) : overview.error && !overview.data ? (
          <ErrorState error={overview.error} onRetry={overview.refresh} />
        ) : !energy ? (
          <EmptyState
            title="No dataset information"
            description="The backend did not return dataset statistics."
            className="min-w-0 py-6"
          />
        ) : (
          <dl className="divide-y divide-line/50">
            <Row label="Coverage">
              <span className="font-mono">
                {formatDateTime(energy.start_timestamp)} → {formatDateTime(energy.end_timestamp)}
              </span>
            </Row>
            <Row label="Stored observations">
              <span className="font-mono">{formatCount(energy.total_observations)}</span>
            </Row>
            <Row label="Total consumption">
              <span className="font-mono">
                {formatKwh(energy.total_consumption_kwh, 1)} kWh
              </span>
            </Row>
            <Row label="Average per observation">
              <span className="font-mono">
                {formatKwh(energy.average_consumption_kwh, 4)} kWh/min
              </span>
            </Row>
            <Row label="Granularity">
              <span className="font-mono">1 minute</span>
            </Row>
            <Row label="Source">
              <span className="font-mono">UCI Individual household power consumption</span>
            </Row>
          </dl>
        )}
      </Card>

      {/* Application */}
      <Card
        title="Application"
        subtitle="EcoPulse AI frontend"
        className="lg:col-span-2"
        action={<SectionIcon icon={Activity} />}
      >
        <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
          <dl className="divide-y divide-line/50">
            <Row label="Name">{siteConfig.name}</Row>
            <Row label="Version">{siteConfig.version}</Row>
            <Row label="Phase">6 — Frontend dashboard and API integration</Row>
            <Row label="Theme">
              <span className="inline-flex items-center gap-1.5">
                <Palette className="size-3 text-muted" aria-hidden />
                Dark (fixed)
              </span>
            </Row>
          </dl>
          <dl className="divide-y divide-line/50">
            <Row label="Framework">Next.js + TypeScript</Row>
            <Row label="Styling">Tailwind CSS</Row>
            <Row label="Charts">Recharts</Row>
            <Row label="Data source">Phase 5 FastAPI backend</Row>
          </dl>
        </div>
        <p className="mt-3 rounded-lg border border-line/70 bg-canvas/60 px-3.5 py-2.5 text-[11px] leading-5 text-muted">
          All dashboard values are read live from the backend. No sample datasets, cached
          fixtures or simulated metrics are bundled with this application.
        </p>
      </Card>
    </div>
  );
}
