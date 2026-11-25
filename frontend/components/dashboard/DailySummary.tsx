"use client";

import { Card } from "@/components/ui/Card";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useEnergySeries } from "@/hooks/useEnergyData";
import { formatDate, formatKwh } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import type { EnergyAggregatePoint } from "@/types/energy";

/**
 * Daily consumption summary: total, average, highest and lowest day within
 * the fetched daily series (backend aggregates only).
 */
export function DailySummary() {
  const { series, loading, error, refresh } = useEnergySeries("daily");

  const items = series.items;
  const stats = items.length > 0 ? computeStats(items) : null;

  return (
    <Card
      title="Daily summary"
      subtitle="Statistics across the days in view"
      action={
        stats ? (
          <span className="chip">
            {items.length} {items.length === 1 ? "day" : "days"}
          </span>
        ) : undefined
      }
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : loading ? (
        <ChartSkeleton height={132} />
      ) : !stats ? (
        <EmptyState
          title="No daily data"
          description="No daily aggregates are available for this range."
          className="min-h-0 py-6"
        />
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3.5">
          <Stat label="Total" value={`${formatKwh(stats.total)} kWh`} />
          <Stat label="Daily average" value={`${formatKwh(stats.average)} kWh`} />
          <Stat
            label="Highest day"
            value={`${formatKwh(stats.max)} kWh`}
            detail={stats.maxAt ? formatDate(stats.maxAt) : undefined}
            highlight
          />
          <Stat
            label="Lowest day"
            value={`${formatKwh(stats.min)} kWh`}
            detail={stats.minAt ? formatDate(stats.minAt) : undefined}
          />
        </dl>
      )}
    </Card>
  );
}

interface Stats {
  total: number;
  average: number;
  max: number;
  min: number;
  maxAt?: string;
  minAt?: string;
}

function computeStats(items: EnergyAggregatePoint[]): Stats {
  let total = 0;
  let max = -Infinity;
  let min = Infinity;
  let maxAt: string | undefined;
  let minAt: string | undefined;

  for (const point of items) {
    total += point.consumption_kwh;
    if (point.consumption_kwh > max) {
      max = point.consumption_kwh;
      maxAt = point.period_start;
    }
    if (point.consumption_kwh < min) {
      min = point.consumption_kwh;
      minAt = point.period_start;
    }
  }

  return {
    total,
    average: total / items.length,
    max,
    min,
    maxAt,
    minAt,
  };
}

function Stat({
  label,
  value,
  detail,
  highlight = false,
}: {
  label: string;
  value: string;
  detail?: string;
  highlight?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted/80">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 truncate font-mono text-[13px]",
          highlight ? "text-primary" : "text-ink",
        )}
      >
        {value}
      </dd>
      {detail ? <dd className="truncate text-[10px] text-muted/70">{detail}</dd> : null}
    </div>
  );
}
