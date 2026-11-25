"use client";

import { useMemo, useState } from "react";

import { AreaChart } from "@/components/charts/AreaChart";
import { BarChart } from "@/components/charts/BarChart";
import { Card } from "@/components/ui/Card";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ErrorState } from "@/components/ui/States";
import { useEnergySeries } from "@/hooks/useEnergyData";
import { formatKwh, formatTick } from "@/lib/formatters";
import type { Granularity } from "@/types/common";

const OPTIONS: ReadonlyArray<{ value: Granularity; label: string }> = [
  { value: "hourly", label: "Hourly" },
  { value: "daily", label: "Daily" },
  { value: "monthly", label: "Monthly" },
];

type AggregateRow = {
  period_start: string;
  consumption_kwh: number;
  is_complete: boolean;
};

const TICK: Record<Granularity, "hour" | "day" | "month"> = {
  hourly: "hour",
  daily: "day",
  monthly: "month",
};

const SUBTITLE: Record<Granularity, string> = {
  hourly: "Consumption per clock hour (kWh)",
  daily: "Consumption per calendar day (kWh)",
  monthly: "Consumption per calendar month (kWh)",
};

/** Main consumption chart with hourly / daily / monthly views. */
export function ConsumptionChart({ flush = false }: { flush?: boolean }) {
  const [granularity, setGranularity] = useState<Granularity>("hourly");
  const { series, loading, error, refresh, refreshing } = useEnergySeries(granularity);

  const rows = useMemo<AggregateRow[]>(
    () =>
      series.items.map((point) => ({
        period_start: point.period_start,
        consumption_kwh: point.consumption_kwh,
        is_complete: point.is_complete,
      })),
    [series.items],
  );

  const incomplete = rows.some((row) => !row.is_complete);

  return (
    <Card
      title="Consumption trend"
      subtitle={SUBTITLE[granularity]}
      flush={flush}
      action={
        <SegmentedControl
          options={OPTIONS}
          value={granularity}
          onChange={setGranularity}
          ariaLabel="Aggregation granularity"
          disabled={loading}
        />
      }
      footer={
        <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
          <span>
            {loading
              ? "Loading…"
              : `${rows.length} ${granularity === "hourly" ? "hours" : granularity === "daily" ? "days" : "months"}`}
            {series.truncated ? " · first page of a longer series" : ""}
          </span>
          {incomplete && !loading ? (
            <span className="text-warning/80">Includes partial periods</span>
          ) : null}
          {!loading && error ? (
            <button
              type="button"
              onClick={refresh}
              className="uppercase text-danger hover:underline"
            >
              Retry
            </button>
          ) : null}
          {refreshing && !loading ? <span>Refreshing…</span> : null}
        </div>
      }
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : granularity === "monthly" ? (
        <BarChart<AggregateRow>
          data={rows}
          xKey="period_start"
          series={[{ dataKey: "consumption_kwh", name: "Consumption" }]}
          height={280}
          loading={loading}
          xTickFormatter={(value) => formatTick(String(value), TICK[granularity])}
          yTickFormatter={(value) => formatKwh(value, 0)}
          tooltipLabelFormatter={(label) => formatTick(String(label), TICK[granularity])}
          tooltipValueFormatter={(value) => `${formatKwh(value)} kWh`}
        />
      ) : (
        <AreaChart<AggregateRow>
          data={rows}
          xKey="period_start"
          valueKey="consumption_kwh"
          name="Consumption"
          height={280}
          loading={loading}
          xTickFormatter={(value) => formatTick(String(value), TICK[granularity])}
          yTickFormatter={(value) => formatKwh(value, value < 1 ? 2 : 1)}
          tooltipLabelFormatter={(label) => formatTick(String(label), TICK[granularity])}
          tooltipValueFormatter={(value) => `${formatKwh(value)} kWh`}
        />
      )}
    </Card>
  );
}
