"use client";

import { Clock, Gauge, TrendingUp } from "lucide-react";

import { MetricCard } from "@/components/dashboard/MetricCard";
import { useConsumptionPatterns } from "@/hooks/useAnalytics";
import { useEnergySummary } from "@/hooks/useEnergyData";
import { formatKw, formatKwh, perMinuteKwhToKw } from "@/lib/formatters";

/**
 * Peak consumption KPI: peak minute power (derived from the backend's
 * per-minute kWh) plus the hour-of-day with the highest average draw.
 */
export function PeakUsageCard({ loading: externalLoading = false }: { loading?: boolean }) {
  const summary = useEnergySummary();
  const patterns = useConsumptionPatterns();

  const peakKwh = summary.data?.maximum_consumption_kwh;
  const peakKw = peakKwh !== undefined ? perMinuteKwhToKw(peakKwh) : null;

  const hourly = patterns.data?.hourly ?? [];
  const peakHour = hourly.length > 0
    ? hourly.reduce((best, point) =>
        point.average_consumption_kwh > best.average_consumption_kwh ? point : best,
      )
    : null;

  const loading = externalLoading || summary.loading || (patterns.loading && !patterns.data);

  return (
    <MetricCard
      label="Peak consumption"
      value={peakKw !== null ? formatKw(peakKw) : "—"}
      unit="kW"
      icon={TrendingUp}
      loading={loading}
      context={
        peakHour
          ? (
              <>
                <Clock className="mr-1 inline size-3" aria-hidden />
                Highest average draw at {String(peakHour.hour).padStart(2, "0")}:00 ·{" "}
                {formatKwh(peakHour.average_consumption_kwh)} kWh/min avg
              </>
            )
          : summary.data
            ? "No hourly pattern available yet"
            : undefined
      }
    />
  );
}

/** Companion card: minimum consumption from the same summary. */
export function MinUsageCard() {
  const summary = useEnergySummary();

  return (
    <MetricCard
      label="Minimum consumption"
      value={summary.data ? formatKwh(summary.data.minimum_consumption_kwh, 3) : "—"}
      unit="kWh/min"
      icon={Gauge}
      loading={summary.loading}
      context={
        summary.data
          ? `Lowest recorded minute · ${summary.data.total_observations.toLocaleString("en-GB")} observations analysed`
          : undefined
      }
    />
  );
}
