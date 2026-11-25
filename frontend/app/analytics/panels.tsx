"use client";

/** Page-scoped panels for the Energy Analytics route. */

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Gauge, Minus, Search, TrendingUp, Activity } from "lucide-react";

import { BarChart } from "@/components/charts/BarChart";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useAnalyticsOverview, useConsumptionPatterns } from "@/hooks/useAnalytics";
import { useEnergyReadings, useEnergySeries, useEnergySummary } from "@/hooks/useEnergyData";
import { useApp } from "@/lib/app-context";
import { chartColors } from "@/lib/chart-theme";
import {
  formatDateTime,
  formatKw,
  formatKwh,
  perMinuteKwhToKw,
} from "@/lib/formatters";
import { shiftDays, dateInputValue, cn } from "@/lib/utils";
import type { HourlyPatternPoint, WeekdayPatternPoint, MonthlyPatternPoint } from "@/types/analytics";

/* ------------------------------------------------------------------ */
/* Period presets                                                      */
/* ------------------------------------------------------------------ */

interface Preset {
  label: string;
  days: number | null;
}

const PRESETS: Preset[] = [
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
  { label: "1Y", days: 365 },
  { label: "All", days: null },
];

/**
 * Quick time-period selector. End bound comes from the real dataset window
 * reported by GET /analytics/overview (the dataset is historical, so
 * "last 30 days" means the 30 days ending on the newest stored reading).
 */
export function PeriodPresets() {
  const { range, setRange } = useApp();
  const overview = useAnalyticsOverview();

  const dataEnd = dateInputValue(overview.data?.energy.end_timestamp);

  const active = useMemo(() => {
    if (!dataEnd) return null;
    if (range.start === undefined && range.end === undefined) return "All";
    for (const preset of PRESETS) {
      if (preset.days === null) {
        if (range.start === undefined && range.end === undefined) return preset.label;
      } else if (range.start === shiftDays(dataEnd, -(preset.days - 1)) && range.end === dataEnd) {
        return preset.label;
      }
    }
    return null;
  }, [range, dataEnd]);

  const apply = (label: string) => {
    const preset = PRESETS.find((entry) => entry.label === label);
    if (!preset) return;
    if (preset.days === null || !dataEnd) {
      setRange({});
      return;
    }
    setRange({ start: shiftDays(dataEnd, -(preset.days - 1)), end: dataEnd });
  };

  return (
    <SegmentedControl
      options={PRESETS.map((preset) => ({ value: preset.label, label: preset.label }))}
      value={active ?? ""}
      onChange={apply}
      ariaLabel="Time period"
      disabled={!dataEnd}
    />
  );
}

/* ------------------------------------------------------------------ */
/* KPI row                                                             */
/* ------------------------------------------------------------------ */

export function AnalyticsKpis() {
  const summary = useEnergySummary();
  const s = summary.data;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="Total energy"
        value={s ? s.total_consumption_kwh.toLocaleString("en-GB", { maximumFractionDigits: 1 }) : "—"}
        unit="kWh"
        icon={Activity}
        loading={summary.loading}
        context={s ? `${s.total_observations.toLocaleString("en-GB")} minute observations in range` : undefined}
      />
      <MetricCard
        label="Average consumption"
        value={s ? formatKwh(s.average_consumption_kwh, 4) : "—"}
        unit="kWh/min"
        icon={Gauge}
        loading={summary.loading}
        context={s ? `≈ ${formatKw(perMinuteKwhToKw(s.average_consumption_kwh))} kW average power` : undefined}
      />
      <MetricCard
        label="Peak usage"
        value={s ? formatKw(perMinuteKwhToKw(s.maximum_consumption_kwh)) : "—"}
        unit="kW"
        icon={TrendingUp}
        loading={summary.loading}
        context={s ? `Highest minute: ${formatKwh(s.maximum_consumption_kwh, 3)} kWh` : undefined}
      />
      <MetricCard
        label="Minimum usage"
        value={s ? formatKwh(s.minimum_consumption_kwh, 4) : "—"}
        unit="kWh/min"
        icon={Minus}
        loading={summary.loading}
        context={s ? `Lowest minute: ${formatKw(perMinuteKwhToKw(s.minimum_consumption_kwh))} kW` : undefined}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Pattern charts                                                      */
/* ------------------------------------------------------------------ */

type HourRow = { label: string; power: number; count: number };

/** Average power by hour of day (kWh/min × 60 = kW). */
export function HourPatternChart() {
  const { data, loading, error, refresh } = useConsumptionPatterns();

  const rows = useMemo<HourRow[]>(
    () =>
      (data?.hourly ?? []).map((point: HourlyPatternPoint) => ({
        label: `${String(point.hour).padStart(2, "0")}:00`,
        power: perMinuteKwhToKw(point.average_consumption_kwh),
        count: point.observation_count,
      })),
    [data],
  );

  return (
    <Card title="Hour-of-day pattern" subtitle="Average power draw per clock hour (kW)">
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : (
        <BarChart<HourRow>
          data={rows}
          xKey="label"
          series={[{ dataKey: "power", name: "Average power", color: chartColors.primary }]}
          height={220}
          loading={loading}
          emptyMessage="No hourly pattern data available."
          yTickFormatter={(value) => formatKw(value, 1)}
          tooltipValueFormatter={(value) => `${formatKw(value)} kW`}
        />
      )}
    </Card>
  );
}

type DayRow = { label: string; power: number; count: number };

/**
 * Weekday vs weekend: per-day averages from the backend, plus the
 * observation-weighted weekday and weekend means computed from them.
 */
export function WeekdayPatternChart() {
  const { data, loading, error, refresh } = useConsumptionPatterns();

  const rows = useMemo<DayRow[]>(() => {
    const weekday = data?.weekday ?? [];
    // Keep Monday-first order regardless of backend numbering.
    const order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    return [...weekday]
      .sort((a, b) => order.indexOf(a.day_name.slice(0, 3)) - order.indexOf(b.day_name.slice(0, 3)))
      .map((point: WeekdayPatternPoint) => ({
        label: point.day_name.slice(0, 3),
        power: perMinuteKwhToKw(point.average_consumption_kwh),
        count: point.observation_count,
      }));
  }, [data]);

  const split = useMemo(() => {
    const weekday = data?.weekday ?? [];
    const mean = (points: WeekdayPatternPoint[]) => {
      const weight = points.reduce((total, point) => total + point.observation_count, 0);
      if (weight === 0) return null;
      return (
        points.reduce(
          (total, point) => total + point.average_consumption_kwh * point.observation_count,
          0,
        ) / weight
      );
    };
    const isWeekend = (name: string) => ["Sat", "Sun"].some((d) => name.startsWith(d));
    const weekendPoints = weekday.filter((point) => isWeekend(point.day_name));
    const weekPoints = weekday.filter((point) => !isWeekend(point.day_name));
    const weekend = mean(weekendPoints);
    const week = mean(weekPoints);
    if (weekend === null || week === null) return null;
    return {
      weekday: perMinuteKwhToKw(week),
      weekend: perMinuteKwhToKw(weekend),
      deltaPct: week !== 0 ? ((weekend - week) / week) * 100 : null,
    };
  }, [data]);

  return (
    <Card
      title="Weekday vs weekend"
      subtitle="Average power by day of week (kW)"
      action={
        split ? (
          <span className="chip">
            {split.deltaPct !== null
              ? `${split.deltaPct >= 0 ? "+" : ""}${split.deltaPct.toFixed(1)}% weekend vs weekday`
              : "—"}
          </span>
        ) : undefined
      }
      footer={
        split ? (
          <div className="flex flex-wrap gap-4 font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
            <span>Weekday avg {formatKw(split.weekday)} kW</span>
            <span>Weekend avg {formatKw(split.weekend)} kW</span>
          </div>
        ) : undefined
      }
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : (
        <BarChart<DayRow>
          data={rows}
          xKey="label"
          series={[{ dataKey: "power", name: "Average power", color: chartColors.accent }]}
          height={220}
          loading={loading}
          emptyMessage="No weekday pattern data available."
          barColor={(row) => (["Sat", "Sun"].includes(row.label) ? chartColors.warning : undefined)}
          yTickFormatter={(value) => formatKw(value, 1)}
          tooltipValueFormatter={(value) => `${formatKw(value)} kW`}
        />
      )}
    </Card>
  );
}

type MonthRow = { label: string; power: number };

/** Seasonal pattern: average power by calendar month. */
export function MonthlyPatternChart() {
  const { data, loading, error, refresh } = useConsumptionPatterns();

  const rows = useMemo<MonthRow[]>(
    () =>
      (data?.monthly ?? []).map((point: MonthlyPatternPoint) => ({
        label: point.month_name.slice(0, 3),
        power: perMinuteKwhToKw(point.average_consumption_kwh),
      })),
    [data],
  );

  return (
    <Card title="Monthly pattern" subtitle="Average power by calendar month (kW)">
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : (
        <BarChart<MonthRow>
          data={rows}
          xKey="label"
          series={[{ dataKey: "power", name: "Average power", color: chartColors.accent }]}
          height={220}
          loading={loading}
          emptyMessage="No monthly pattern data available."
          yTickFormatter={(value) => formatKw(value, 1)}
          tooltipValueFormatter={(value) => `${formatKw(value)} kW`}
        />
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Distribution                                                        */
/* ------------------------------------------------------------------ */

type BinRow = { label: string; days: number };

/**
 * Histogram of daily consumption totals (kWh) built from the real daily
 * aggregates in view — equal-width bins between the lowest and highest day.
 */
export function DailyDistribution() {
  const { series, loading, error, refresh } = useEnergySeries("daily");

  const bins = useMemo<BinRow[]>(() => {
    const values = series.items.map((point) => point.consumption_kwh);
    if (values.length < 2) return [];

    const min = Math.min(...values);
    const max = Math.max(...values);
    const binCount = Math.min(10, Math.max(4, Math.ceil(Math.sqrt(values.length))));
    const width = (max - min) / binCount || 1;

    const counts = Array.from({ length: binCount }, () => 0);
    for (const value of values) {
      const index = Math.min(binCount - 1, Math.floor((value - min) / width));
      counts[index] += 1;
    }

    return counts.map((days, index) => {
      const low = min + index * width;
      const high = low + width;
      return {
        label: `${formatKwh(low, 0)}–${formatKwh(high, 0)}`,
        days,
      };
    });
  }, [series.items]);

  return (
    <Card
      title="Consumption distribution"
      subtitle="Number of days per daily-consumption band (kWh)"
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : (
        <BarChart<BinRow>
          data={bins}
          xKey="label"
          series={[{ dataKey: "days", name: "Days", color: chartColors.primary }]}
          height={220}
          loading={loading}
          emptyMessage="Not enough daily data to build a distribution."
          yTickFormatter={(value) => String(Math.round(value))}
          tooltipValueFormatter={(value, name) =>
            name === "Days" ? `${Math.round(value)} days` : String(value)
          }
        />
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Historical data explorer                                            */
/* ------------------------------------------------------------------ */

const PAGE_SIZE = 25;

/** Paginated minute-level readings table (newest/oldest toggle). */
export function DataExplorer() {
  const { range } = useApp();
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);

  // Reset to the first page whenever the header range changes.
  const rangeKey = `${range.start ?? ""}|${range.end ?? ""}`;
  const [lastRange, setLastRange] = useState(rangeKey);
  if (rangeKey !== lastRange) {
    setLastRange(rangeKey);
    setOffset(0);
  }

  const { data, loading, error, refresh } = useEnergyReadings({
    limit: PAGE_SIZE,
    offset,
    order,
  });

  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const items = data?.items ?? [];

  return (
    <Card
      title="Historical data explorer"
      subtitle="Minute-level readings straight from PostgreSQL"
      action={
        <div className="flex items-center gap-2">
          <Search className="size-3.5 text-muted/70" aria-hidden />
          <SegmentedControl
            options={[
              { value: "desc", label: "Newest" },
              { value: "asc", label: "Oldest" },
            ]}
            value={order}
            onChange={(value) => {
              setOrder(value);
              setOffset(0);
            }}
            ariaLabel="Sort order"
          />
        </div>
      }
      footer={
        <div className="flex items-center justify-between gap-3">
          <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
            {loading
              ? "Loading…"
              : `${total.toLocaleString("en-GB")} rows · page ${page} of ${pageCount}`}
          </p>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={loading || offset === 0}
              aria-label="Previous page"
              className="grid size-7 place-items-center rounded-md border border-line text-muted transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              <ChevronLeft className="size-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={loading || offset + PAGE_SIZE >= total}
              aria-label="Next page"
              className="grid size-7 place-items-center rounded-md border border-line text-muted transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              <ChevronRight className="size-3.5" />
            </button>
          </div>
        </div>
      }
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : loading && items.length === 0 ? (
        <ChartSkeleton height={320} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No readings"
          description="No minute-level readings match the selected date range."
          className="min-h-0 py-8"
        />
      ) : (
        <div className="-mx-5 overflow-x-auto px-5">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Timestamp</th>
                <th scope="col">Energy (kWh)</th>
                <th scope="col">Power (kW)</th>
                <th scope="col">Voltage (V)</th>
                <th scope="col">Intensity (A)</th>
                <th scope="col">Quality</th>
              </tr>
            </thead>
            <tbody>
              {items.map((reading) => (
                <tr key={reading.id}>
                  <td className="font-mono text-[11px]">{formatDateTime(reading.timestamp)}</td>
                  <td className="font-mono">{formatKwh(reading.energy_consumption_kwh, 4)}</td>
                  <td className="font-mono">{formatKw(reading.global_active_power)}</td>
                  <td className="font-mono">{reading.voltage.toFixed(1)}</td>
                  <td className="font-mono">{reading.global_intensity.toFixed(1)}</td>
                  <td>
                    {reading.is_imputed ? (
                      <Badge tone="warning">imputed</Badge>
                    ) : (
                      <Badge tone="ok">measured</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className={cn("mt-3 font-mono text-[9px] uppercase tracking-[0.1em] text-muted/60")}>
        Range follows the header date filter
      </p>
    </Card>
  );
}
