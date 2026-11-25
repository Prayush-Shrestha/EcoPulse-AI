"use client";

import { useMemo } from "react";

import { LineChart } from "@/components/charts/LineChart";
import { chartColors } from "@/lib/chart-theme";
import { formatKwh, formatTick } from "@/lib/formatters";
import type { EnergyAggregatePoint } from "@/types/energy";

type ForecastRow = {
  ts: string;
  predicted: number | null;
  actual: number | null;
};

/**
 * Join predicted points with actual hourly consumption on their shared
 * timestamp. Actuals are null wherever no measurement exists (future hours).
 */
function mergeForecastRows(
  predicted: ReadonlyArray<{ forecast_timestamp: string; predicted_energy_kwh: number }>,
  actual: EnergyAggregatePoint[],
): ForecastRow[] {
  const rows = new Map<string, ForecastRow>();

  for (const point of predicted) {
    rows.set(point.forecast_timestamp, {
      ts: point.forecast_timestamp,
      predicted: point.predicted_energy_kwh,
      actual: null,
    });
  }

  for (const point of actual) {
    const existing = rows.get(point.period_start);
    if (existing) {
      existing.actual = point.consumption_kwh;
    } else {
      rows.set(point.period_start, {
        ts: point.period_start,
        predicted: null,
        actual: point.consumption_kwh,
      });
    }
  }

  return [...rows.values()].sort((a, b) => a.ts.localeCompare(b.ts));
}

function Legend({ showActual }: { showActual: boolean }) {
  return (
    <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[9px] uppercase tracking-[0.1em] text-muted">
      <span className="flex items-center gap-1.5">
        <span className="h-0.5 w-4 rounded" style={{ backgroundColor: chartColors.actual }} aria-hidden />
        Actual
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className="h-0.5 w-4 rounded"
          style={{
            backgroundImage: `repeating-linear-gradient(to right, ${chartColors.primary} 0 5px, transparent 5px 9px)`,
          }}
          aria-hidden
        />
        Predicted
      </span>
      {!showActual && (
        <span className="text-muted/60">No actuals overlap this window</span>
      )}
    </div>
  );
}

interface ForecastChartProps {
  /** Stored records or fresh prediction points (timestamp + value). */
  predicted: ReadonlyArray<{ forecast_timestamp: string; predicted_energy_kwh: number }>;
  actual?: EnergyAggregatePoint[];
  loading?: boolean;
  height?: number;
  emptyMessage?: string;
}

/** Actual-vs-predicted line chart shared by the overview and forecasting pages. */
export function ForecastChart({
  predicted,
  actual = [],
  loading = false,
  height = 280,
  emptyMessage = "Generate or load a forecast to see predictions here.",
}: ForecastChartProps) {
  const rows = useMemo(() => mergeForecastRows(predicted, actual), [predicted, actual]);
  const showActual = rows.some((row) => row.actual !== null);

  return (
    <div>
      {!loading && rows.length > 0 && <Legend showActual={showActual} />}
      <LineChart<ForecastRow>
        data={rows}
        xKey="ts"
        loading={loading}
        height={height}
        emptyMessage={emptyMessage}
        series={[
          {
            dataKey: "actual",
            name: "Actual",
            color: chartColors.actual,
            strokeWidth: 1.6,
          },
          {
            dataKey: "predicted",
            name: "Predicted",
            color: chartColors.primary,
            dashed: true,
            strokeWidth: 1.8,
          },
        ]}
        yTickFormatter={(value) => formatKwh(value, 2)}
        xTickFormatter={(value) => formatTick(String(value), "hour")}
        tooltipLabelFormatter={(label) => formatTick(String(label), "hour")}
        tooltipValueFormatter={(value) => `${formatKwh(value)} kWh`}
      />
    </div>
  );
}
