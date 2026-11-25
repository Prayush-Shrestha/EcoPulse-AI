"use client";

/** Interactive forecasting workspace: horizon selection + real predict call. */

import { useMemo, useState, type ReactNode } from "react";
import { Cpu, Info, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";

import { ForecastChart } from "@/components/dashboard/ForecastChart";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useEnergyActuals } from "@/hooks/useEnergyData";
import { useForecastHistory, usePredictForecast } from "@/hooks/useForecasts";
import { useModels } from "@/hooks/useModels";
import { formatDateTime, formatKwh, formatCount } from "@/lib/formatters";
import { SUPPORTED_HORIZONS, type HorizonHours } from "@/types/forecast";

const HORIZON_LABELS: Record<HorizonHours, string> = {
  1: "1 hour",
  6: "6 hours",
  24: "24 hours",
  48: "48 hours",
};

type MetricRow = {
  label: string;
  value: string;
};

export function ForecastWorkspace() {
  const [horizon, setHorizon] = useState<HorizonHours>(24);
  const predict = usePredictForecast();
  const history = useForecastHistory({ limit: 500 });
  const models = useModels();

  const generated = predict.result;
  const stored = useMemo(
    () =>
      [...(history.data?.items ?? [])].sort((a, b) =>
        a.forecast_timestamp.localeCompare(b.forecast_timestamp),
      ),
    [history.data],
  );

  // Plot the fresh prediction when present, otherwise the stored history.
  const active = generated ? generated.items : stored;
  const baseTimestamp = generated?.base_timestamp ?? stored[0]?.forecast_timestamp;
  const lastTimestamp = active.length > 0 ? active[active.length - 1].forecast_timestamp : undefined;

  const actuals = useEnergyActuals(baseTimestamp, lastTimestamp);

  const model = models.data?.models.find((entry) => entry.key === "forecasting");

  const summary = useMemo<MetricRow[]>(() => {
    if (active.length === 0) return [];
    const values = active.map((point) => point.predicted_energy_kwh);
    const total = values.reduce((sum, value) => sum + value, 0);
    const horizonHours = generated?.horizon_hours ?? stored[stored.length - 1]?.forecast_horizon ?? null;
    return [
      { label: "Predicted total", value: `${formatKwh(total)} kWh` },
      { label: "Predicted average", value: `${formatKwh(total / values.length)} kWh` },
      { label: "Predicted peak", value: `${formatKwh(Math.max(...values))} kWh` },
      { label: "Forecast horizon", value: horizonHours !== null ? `${horizonHours} h` : "—" },
    ];
  }, [active, generated, stored]);

  const loading = history.loading && !history.data;
  const chartLoading = history.loading || (active.length > 0 && actuals.loading);

  return (
    <div className="space-y-4">
      {/* Controls + model info */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <Card
            title="Generate forecast"
            subtitle="Runs the saved Phase 4 model against PostgreSQL — no simulated data"
            action={
              <SegmentedControl
                options={SUPPORTED_HORIZONS.map((value) => ({
                  value,
                  label: HORIZON_LABELS[value],
                }))}
                value={horizon}
                onChange={setHorizon}
                ariaLabel="Forecast horizon"
                disabled={predict.pending}
              />
            }
          >
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => predict.predict(horizon)}
                disabled={predict.pending}
                className="btn-primary !px-4 !py-2.5 text-xs disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Sparkles className="size-3.5" aria-hidden />
                {predict.pending ? "Generating…" : `Generate ${HORIZON_LABELS[horizon]} forecast`}
              </button>

              {generated && !predict.pending ? (
                <Badge tone="ok" dot>
                  generated {formatDateTime(generated.generated_at)}
                </Badge>
              ) : null}

              {predict.pending ? (
                <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted">
                  Recursion running — up to 45 s
                </span>
              ) : null}
            </div>

            {predict.error ? (
              <div
                role="alert"
                className="mt-4 flex items-start gap-3 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3"
              >
                <TriangleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-danger">Forecast generation failed</p>
                  <p className="mt-1 break-words text-xs leading-5 text-muted">
                    {predict.error.message}
                  </p>
                </div>
              </div>
            ) : null}

            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-line/50 pt-4 sm:grid-cols-4">
              <Meta
                label="Model"
                value={generated?.model_name ?? model?.name ?? "—"}
              />
              <Meta
                label="Version"
                value={generated?.model_version ?? model?.version ?? "—"}
              />
              <Meta
                label="Base hour"
                value={generated ? formatDateTime(generated.base_timestamp) : "—"}
              />
              <Meta
                label="Generated at"
                value={generated ? formatDateTime(generated.generated_at) : "stored history"}
              />
            </dl>
          </Card>
        </div>

        <div className="min-w-0">
          <Card title="Model information" subtitle="Loaded Phase 4 artefact">
            {models.loading && !models.data ? (
              <ChartSkeleton height={150} />
            ) : models.error && !models.data ? (
              <ErrorState error={models.error} onRetry={models.refresh} />
            ) : !model ? (
              <EmptyState
                title="Forecasting model unavailable"
                description="The backend did not return a loaded forecasting model."
                className="min-h-0 py-6"
              />
            ) : (
              <ul className="space-y-2 text-xs">
                <MetaRow label="Status">
                  <Badge tone={model.status === "loaded" ? "ok" : "warning"}>
                    {model.status}
                  </Badge>
                </MetaRow>
                <MetaRow label="Type">{model.model_type ?? "—"}</MetaRow>
                <MetaRow label="Target">{model.target ?? "—"}</MetaRow>
                <MetaRow label="Features">
                  {model.feature_count !== null ? formatCount(model.feature_count) : "—"}
                </MetaRow>
                <MetaRow label="Trained">
                  {model.trained_at_utc ? formatDateTime(model.trained_at_utc) : "—"}
                </MetaRow>
                {model.metrics
                  ? Object.entries(model.metrics).map(([name, value]) => (
                      <MetaRow key={name} label={name}>
                        <span className="font-mono">{value.toFixed(4)}</span>
                      </MetaRow>
                    ))
                  : null}
                {model.detail ? (
                  <li className="flex items-start gap-2 pt-1 text-[11px] text-muted/80">
                    <Info className="mt-0.5 size-3 shrink-0" aria-hidden />
                    {model.detail}
                  </li>
                ) : null}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {/* Summary cards */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <MetricCard key={index} label="" value="" icon={Cpu} loading />
          ))}
        </div>
      ) : summary.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {summary.map((row, index) => (
            <MetricCard
              key={row.label}
              label={row.label}
              value={row.value}
              icon={index === 3 ? RefreshCw : Cpu}
              context={
                generated
                  ? `From the response generated ${formatDateTime(generated.generated_at)}`
                  : `From ${formatCount(stored.length)} stored forecast points`
              }
            />
          ))}
        </div>
      ) : null}

      {/* Chart */}
      <Card
        title="Forecast timeline"
        subtitle={
          generated
            ? `Fresh prediction · ${generated.horizon_hours} h horizon from ${formatDateTime(generated.base_timestamp)}`
            : "Most recent stored predictions vs actual consumption"
        }
        action={
          <button
            type="button"
            onClick={history.refresh}
            disabled={history.refreshing || history.loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-muted transition-colors hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <RefreshCw
              className={`size-3 ${history.refreshing ? "animate-spin" : ""}`}
              aria-hidden
            />
            Refresh
          </button>
        }
        footer={
          <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
            {formatCount(history.data?.total ?? 0)} stored forecast points ·
            predictions are model output, not measurements
          </p>
        }
      >
        {history.error && !history.loading ? (
          <ErrorState error={history.error} onRetry={history.refresh} />
        ) : active.length === 0 && !chartLoading ? (
          <EmptyState
            title="No forecasts yet"
            description="Choose a horizon and generate a forecast — the backend will persist every prediction."
          />
        ) : (
          <ForecastChart
            predicted={active}
            actual={actuals.data?.items ?? []}
            loading={chartLoading}
            height={320}
          />
        )}
      </Card>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted/80">
        {label}
      </dt>
      <dd className="mt-1 truncate text-xs text-ink">{value}</dd>
    </div>
  );
}

function MetaRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="text-muted">{label}</span>
      <span className="min-w-0 truncate text-right text-ink">{children}</span>
    </li>
  );
}
