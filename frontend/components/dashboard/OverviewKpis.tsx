"use client";

import { Activity, Gauge, TriangleAlert, Zap } from "lucide-react";

import { MetricCard } from "@/components/dashboard/MetricCard";
import { useAnalyticsOverview } from "@/hooks/useAnalytics";
import { useEnergySummary } from "@/hooks/useEnergyData";
import { formatCount, formatDate, formatKw, formatPercent, perMinuteKwhToKw } from "@/lib/formatters";

/**
 * Four overview KPIs. Consumption metrics follow the header date range;
 * anomaly counts come from the analytics overview (whole dataset).
 */
export function OverviewKpis() {
  const summary = useEnergySummary();
  const overview = useAnalyticsOverview();

  const s = summary.data;
  const a = overview.data?.anomaly;

  const windowLabel = s?.start_timestamp
    ? `${formatDate(s.start_timestamp)} – ${s.end_timestamp ? formatDate(s.end_timestamp) : "now"}`
    : "All recorded data";

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="Total consumption"
        value={s ? s.total_consumption_kwh.toLocaleString("en-GB", { maximumFractionDigits: 1 }) : "—"}
        unit="kWh"
        icon={Zap}
        loading={summary.loading}
        context={
          s
            ? `${windowLabel} · ${formatCount(s.total_observations)} observations`
            : undefined
        }
      />
      <MetricCard
        label="Average power"
        value={s ? formatKw(perMinuteKwhToKw(s.average_consumption_kwh)) : "—"}
        unit="kW"
        icon={Activity}
        loading={summary.loading}
        context={
          s
            ? `Mean of ${formatCount(s.total_observations)} minute readings in range`
            : undefined
        }
      />
      <MetricCard
        label="Peak consumption"
        value={s ? formatKw(perMinuteKwhToKw(s.maximum_consumption_kwh)) : "—"}
        unit="kW"
        icon={Gauge}
        loading={summary.loading}
        context={
          s
            ? `Highest single minute (${s.maximum_consumption_kwh.toFixed(3)} kWh/min)`
            : undefined
        }
      />
      <MetricCard
        label="Detected anomalies"
        value={a ? formatCount(a.total_anomalies) : "—"}
        unit="records"
        icon={TriangleAlert}
        tone={a && a.total_anomalies > 0 ? "warning" : "default"}
        loading={overview.loading}
        context={
          a
            ? a.total_anomalies > 0
              ? `${formatPercent(a.anomaly_percentage)} of ${formatCount(a.total_observations)} analysed observations · last ${a.latest_detected_at ? formatDate(a.latest_detected_at) : "—"}`
              : `0 anomalies across ${formatCount(a.total_observations)} analysed observations`
            : undefined
        }
      />
    </div>
  );
}
