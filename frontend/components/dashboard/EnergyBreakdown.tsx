"use client";

import { useMemo } from "react";

import { BarChart } from "@/components/charts/BarChart";
import { Card } from "@/components/ui/Card";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { useEnergyReadings } from "@/hooks/useEnergyData";
import { formatKwh } from "@/lib/formatters";
import { chartColors } from "@/lib/chart-theme";

type Segment = {
  label: string;
  kwh: number;
  share: number;
  color: string;
};

const COLORS = [chartColors.primary, chartColors.accent, chartColors.warning, chartColors.muted];

/**
 * Sub-metering breakdown computed from real minute readings returned by
 * GET /api/v1/energy. Sub-meter values are Wh per minute; everything not
 * covered by a sub-meter is reported as "other loads".
 */
export function EnergyBreakdown() {
  const { data, loading, error, refresh } = useEnergyReadings({
    limit: 1440, // most recent day of minutes
    order: "desc",
  });

  const segments = useMemo<Segment[]>(() => {
    const items = data?.items ?? [];
    if (items.length === 0) return [];

    let sub1 = 0;
    let sub2 = 0;
    let sub3 = 0;
    let total = 0;
    for (const reading of items) {
      sub1 += reading.sub_metering_1;
      sub2 += reading.sub_metering_2;
      sub3 += reading.sub_metering_3;
      total += reading.energy_consumption_kwh * 1000; // kWh → Wh
    }

    const other = Math.max(0, total - sub1 - sub2 - sub3);
    const raw: Array<{ label: string; wh: number }> = [
      { label: "Sub-meter 1 (laundry)", wh: sub1 },
      { label: "Sub-meter 2 (climate)", wh: sub2 },
      { label: "Sub-meter 3 (kitchen)", wh: sub3 },
      { label: "Other loads", wh: other },
    ];

    return raw
      .filter((entry) => entry.wh > 0)
      .map((entry, index) => ({
        label: entry.label,
        kwh: entry.wh / 1000,
        share: total > 0 ? (entry.wh / total) * 100 : 0,
        color: COLORS[index % COLORS.length],
      }));
  }, [data]);

  const coverage = data
    ? `${data.items.length.toLocaleString("en-GB")} recent minute readings`
    : null;

  return (
    <Card
      title="Energy distribution"
      subtitle={`Sub-metered vs unmetered loads · ${coverage ?? "…"}`}
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : loading ? (
        <ChartSkeleton height={180} />
      ) : segments.length === 0 ? (
        <EmptyState
          title="No readings"
          description="No minute-level readings are available for the current range."
          className="min-h-0 py-6"
        />
      ) : (
        <>
          <BarChart<Segment>
            data={segments}
            xKey="label"
            series={[{ dataKey: "kwh", name: "Consumption" }]}
            height={150}
            yTickFormatter={(value) => formatKwh(value, 1)}
            tooltipValueFormatter={(value) => `${formatKwh(value)} kWh`}
            barColor={(row) => row.color}
            radius={4}
          />
          <ul className="mt-3 space-y-2">
            {segments.map((segment) => (
              <li key={segment.label} className="flex items-center gap-2.5 text-xs">
                <span
                  className="size-2 shrink-0 rounded-sm"
                  style={{ backgroundColor: segment.color }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1 truncate text-muted">{segment.label}</span>
                <span className="font-mono text-[11px] text-ink">
                  {formatKwh(segment.kwh)} kWh
                </span>
                <span className="w-12 text-right font-mono text-[11px] text-muted">
                  {segment.share.toFixed(1)}%
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
