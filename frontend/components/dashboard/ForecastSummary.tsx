"use client";

import Link from "next/link";
import { ArrowUpRight, CalendarClock, Cpu, Sigma, Zap } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useForecastVsActual } from "@/hooks/useForecasts";
import { useModels } from "@/hooks/useModels";
import { formatDateTime, formatKwh } from "@/lib/formatters";

interface Stat {
  label: string;
  value: string;
  icon: typeof Sigma;
}

/**
 * Forecast overview: stored predictions joined with actuals, plus summary
 * metrics computed from the real prediction rows.
 */
export function ForecastSummary() {
  const { predicted, loading, error, refresh } = useForecastVsActual({ limit: 500 });
  const models = useModels();

  const latest = predicted.length > 0 ? predicted[predicted.length - 1] : null;
  const horizon = latest?.forecast_horizon ?? null;

  const stats: Stat[] = latest
    ? [
        {
          label: "Predicted total",
          value: `${formatKwh(sum(predicted))} kWh`,
          icon: Sigma,
        },
        {
          label: "Predicted average",
          value: `${formatKwh(sum(predicted) / predicted.length)} kWh`,
          icon: CalendarClock,
        },
        {
          label: "Predicted peak",
          value: `${formatKwh(Math.max(...predicted.map((p) => p.predicted_energy_kwh)))} kWh`,
          icon: Zap,
        },
        {
          label: "Horizon",
          value: `${horizon} h`,
          icon: CalendarClock,
        },
      ]
    : [];

  const forecastingModel = models.data?.models.find((m) => m.key === "forecasting");

  return (
    <Card
      title="Forecast overview"
      subtitle={
        latest
          ? `Latest stored prediction · generated from ${formatDateTime(latest.created_at)}`
          : "Most recent persisted forecast"
      }
      action={
        <Link
          href="/forecasting"
          className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted transition-colors hover:text-ink"
        >
          Open
          <ArrowUpRight className="size-3" aria-hidden />
        </Link>
      }
      footer={
        latest ? (
          <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
            <span className="flex items-center gap-1.5">
              <Cpu className="size-3" aria-hidden />
              {latest.model_name} · v{latest.model_version}
            </span>
            <span>
              {predicted.length} point{predicted.length === 1 ? "" : "s"} in history
            </span>
          </div>
        ) : undefined
      }
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : loading ? (
        <ChartSkeleton height={140} />
      ) : !latest ? (
        <EmptyState
          title="No forecasts yet"
          description="Generate a forecast on the Forecasting page; predictions are then stored by the backend."
          className="min-h-0 py-7"
          action={
            <Link href="/forecasting" className="btn-secondary !px-4 !py-2 text-xs">
              Go to Forecasting
            </Link>
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4">
            {stats.map((stat) => {
              const Icon = stat.icon;
              return (
                <div key={stat.label} className="min-w-0">
                  <p className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted/80">
                    <Icon className="size-3" aria-hidden />
                    {stat.label}
                  </p>
                  <p className="mt-1 truncate font-mono text-[15px] text-ink">{stat.value}</p>
                </div>
              );
            })}
          </div>
          {forecastingModel ? (
            <p className="mt-3 flex items-center gap-2 border-t border-line/50 pt-2.5 text-[10px] text-muted">
              <Badge tone={forecastingModel.status === "loaded" ? "ok" : "warning"}>
                {forecastingModel.status}
              </Badge>
              {forecastingModel.name}
              {forecastingModel.version ? ` v${forecastingModel.version}` : ""}
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}

function sum(points: Array<{ predicted_energy_kwh: number }>): number {
  return points.reduce((total, point) => total + point.predicted_energy_kwh, 0);
}
