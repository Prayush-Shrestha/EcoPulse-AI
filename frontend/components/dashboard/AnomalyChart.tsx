"use client";

import { useMemo, type ReactNode } from "react";
import { ReferenceLine } from "recharts";

import { LineChart } from "@/components/charts/LineChart";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { useAnomalyHistory } from "@/hooks/useAnomalies";
import { useEnergySeries } from "@/hooks/useEnergyData";
import { chartColors } from "@/lib/chart-theme";
import { formatKwh, formatScore, formatTick } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import type { AnomalyRecord } from "@/types/anomaly";
import type { Granularity } from "@/types/common";

type ChartRow = {
  ts: string;
  consumption: number | null;
  anomalyScore: number | null;
  isAnomaly: boolean;
};

interface AnomalyChartProps {
  /** Aggregate series granularity. Anomalies are marked at their hour. */
  granularity?: Granularity;
  /** Show the score axis instead of consumption. */
  mode?: "consumption" | "score";
  height?: number;
  /** Extra header controls (e.g. a view toggle). */
  controls?: ReactNode;
}

/**
 * Consumption trend with detected anomalies overlaid:
 * - consumption mode: anomaly markers sit on the trend line
 * - score mode: scores plotted with a threshold reference line
 *
 * Anomalies are minute-level; they are joined to the series by their
 * containing period so markers land on the right x position.
 */
export function AnomalyChart({ granularity = "hourly", mode = "consumption", height = 280, controls }: AnomalyChartProps) {
  const { series, loading: seriesLoading, error: seriesError, refresh: refreshSeries } = useEnergySeries(granularity);
  const anomalies = useAnomalyHistory({ is_anomaly: true, limit: 500 });

  const rows = useMemo<ChartRow[]>(() => {
    const detected = anomalies.data?.items ?? [];
    // Map hour bucket → anomalies falling inside it.
    const bucket = new Map<string, AnomalyRecord[]>();
    for (const record of detected) {
      const key = periodKey(record.observation_timestamp, granularity);
      const list = bucket.get(key);
      if (list) list.push(record);
      else bucket.set(key, [record]);
    }

    return series.items.map((point) => {
      const inBucket = bucket.get(point.period_start) ?? [];
      const worst = inBucket.reduce<AnomalyRecord | null>(
        (current, record) =>
          !current || record.anomaly_score < current.anomaly_score ? record : current,
        null,
      );
      return {
        ts: point.period_start,
        consumption: point.consumption_kwh,
        anomalyScore: worst ? worst.anomaly_score : null,
        isAnomaly: worst !== null,
      };
    });
  }, [series.items, anomalies.data, granularity]);

  const scores = rows.filter((row) => row.anomalyScore !== null).map((row) => row.anomalyScore as number);
  const minScore = scores.length > 0 ? Math.min(...scores) : null;
  const anomalyCount = rows.filter((row) => row.isAnomaly).length;

  const loading = seriesLoading || (anomalies.loading && !anomalies.data);
  const error = seriesError ?? anomalies.error;

  const tick = granularity === "hourly" ? "hour" : granularity === "monthly" ? "month" : "day";

  return (
    <Card
      title={mode === "score" ? "Anomaly scores" : "Consumption with detected anomalies"}
      subtitle={
        mode === "score"
          ? "Anomaly score per period — lower scores indicate stronger deviations"
          : "Red markers highlight periods containing at least one detected anomaly"
      }
      action={
        <div className="flex flex-wrap items-center gap-2">
          {controls}
          {anomalyCount > 0 ? (
            <span className="chip border-danger/30 text-danger">
              {anomalyCount} {anomalyCount === 1 ? "period" : "periods"}
            </span>
          ) : undefined}
        </div>
      }
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={() => { refreshSeries(); anomalies.refresh(); }} />
      ) : mode === "score" ? (
        <LineChart<ChartRow>
          data={rows}
          xKey="ts"
          height={height}
          loading={loading}
          emptyMessage="No anomaly scores recorded for this range."
          series={[
            {
              dataKey: "anomalyScore",
              name: "Anomaly score",
              color: chartColors.danger,
              showDot: true,
              strokeWidth: 1.4,
            },
          ]}
          yDomain={minScore !== null ? [minScore * 1.1, 0] : undefined}
          xTickFormatter={(value) => formatTick(String(value), tick)}
          yTickFormatter={(value) => formatScore(value)}
          tooltipLabelFormatter={(label) => formatTick(String(label), tick)}
          tooltipValueFormatter={(value) => formatScore(value)}
        >
          {minScore !== null && (
            <ReferenceLine
              y={minScore}
              stroke={chartColors.warning}
              strokeDasharray="4 4"
              label={{
                value: `threshold ${formatScore(minScore)}`,
                position: "insideTopRight",
                fill: chartColors.warning,
                fontSize: 10,
                fontFamily: "var(--font-geist-mono)",
              }}
            />
          )}
        </LineChart>
      ) : (
        <LineChart<ChartRow>
          data={rows}
          xKey="ts"
          height={height}
          loading={loading}
          emptyMessage="No consumption data for this range."
          series={[
            {
              dataKey: "consumption",
              name: "Consumption",
              color: chartColors.actual,
              strokeWidth: 1.5,
            },
          ]}
          xTickFormatter={(value) => formatTick(String(value), tick)}
          yTickFormatter={(value) => formatKwh(value, value < 1 ? 2 : 1)}
          tooltipLabelFormatter={(label) => formatTick(String(label), tick)}
          tooltipValueFormatter={(value, name) =>
            name === "Anomaly score" ? formatScore(value) : `${formatKwh(value)} kWh`
          }
        />
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
        <span className={cn("flex items-center gap-1.5", !loading && anomalyCount === 0 && "opacity-60")}>
          <span className={cn("size-1.5 rounded-full", anomalyCount > 0 ? "bg-danger" : "bg-line")} aria-hidden />
          {anomalyCount > 0 ? `${anomalyCount} periods flagged` : "No anomalies in view"}
        </span>
        <span>Results are detected anomalies, not confirmed faults</span>
      </div>
    </Card>
  );
}

/** Bucket an observation timestamp to the aggregate period key. */
function periodKey(iso: string, granularity: Granularity): string {
  if (granularity === "hourly") return `${iso.slice(0, 13)}:00:00`;
  if (granularity === "daily") return `${iso.slice(0, 10)}T00:00:00`;
  return `${iso.slice(0, 7)}-01T00:00:00`;
}
