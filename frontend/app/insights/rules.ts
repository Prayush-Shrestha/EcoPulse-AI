/**
 * Explainable insight rules.
 *
 * Every insight is a deterministic transformation of real backend analytics
 * (consumption patterns, overview trends, anomaly summary). No probabilistic
 * or language-model generation is involved — each rule states the arithmetic
 * it performed so the result stays auditable.
 */

import type { AnalyticsOverviewResponse, ConsumptionPatternsResponse } from "@/types/analytics";
import type { AnomalySummaryResponse } from "@/types/anomaly";

export type InsightType =
  | "peak"
  | "low"
  | "pattern"
  | "comparison"
  | "change"
  | "anomaly";

export interface Insight {
  id: string;
  type: InsightType;
  title: string;
  /** Plain-language explanation of what the rule found. */
  explanation: string;
  /** Supporting numbers, each derived from backend responses. */
  bullets: string[];
  /** The time window the numbers come from. */
  period: string;
}

export const TYPE_LABELS: Record<InsightType, string> = {
  peak: "Peak period",
  low: "Low-consumption period",
  pattern: "Usage pattern",
  comparison: "Weekday vs weekend",
  change: "Consumption change",
  anomaly: "Unusual usage",
};

function kW(perMinuteKwh: number): number {
  return perMinuteKwh * 60;
}

function fmtKw(value: number): string {
  return value.toLocaleString("en-GB", { maximumFractionDigits: 2 });
}

function fmtNum(value: number, decimals = 1): string {
  return value.toLocaleString("en-GB", { maximumFractionDigits: decimals });
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(match[3])} ${months[Number(match[2]) - 1]} ${match[1]}`;
}

interface Inputs {
  overview: AnalyticsOverviewResponse;
  patterns: ConsumptionPatternsResponse;
  anomalySummary: AnomalySummaryResponse | null;
  /** Header-selected range label, when the user filtered the data. */
  rangeLabel?: string;
  rangeTotals?: { totalKwh: number; observations: number } | null;
}

export function buildInsights({
  overview,
  patterns,
  anomalySummary,
  rangeLabel,
  rangeTotals,
}: Inputs): Insight[] {
  const insights: Insight[] = [];
  const datasetPeriod = `${fmtDate(overview.energy.start_timestamp)} – ${fmtDate(overview.energy.end_timestamp)}`;

  /* ---- Hour-of-day peak and trough ---- */
  const hourly = patterns.hourly;
  if (hourly.length > 0) {
    const weight = hourly.reduce((sum, point) => sum + point.observation_count, 0);
    const meanPerMinute =
      weight > 0
        ? hourly.reduce((sum, point) => sum + point.average_consumption_kwh * point.observation_count, 0) / weight
        : hourly.reduce((sum, point) => sum + point.average_consumption_kwh, 0) / hourly.length;

    const peak = hourly.reduce((best, point) =>
      point.average_consumption_kwh > best.average_consumption_kwh ? point : best,
    );
    const trough = hourly.reduce((best, point) =>
      point.average_consumption_kwh < best.average_consumption_kwh ? point : best,
    );

    const peakKw = kW(peak.average_consumption_kwh);
    const meanKw = kW(meanPerMinute);
    const troughKw = kW(trough.average_consumption_kwh);
    const peakDelta = meanKw > 0 ? ((peakKw - meanKw) / meanKw) * 100 : 0;
    const troughDelta = meanKw > 0 ? ((troughKw - meanKw) / meanKw) * 100 : 0;

    insights.push({
      id: "peak-hour",
      type: "peak",
      title: `Demand peaks at ${String(peak.hour).padStart(2, "0")}:00`,
      explanation: `Across the dataset, the hour from ${String(peak.hour).padStart(2, "0")}:00 to ${String((peak.hour + 1) % 24).padStart(2, "0")}:00 carries the highest average power draw — ${fmtNum(peakDelta, 1)}% above the 24-hour mean.`,
      bullets: [
        `Peak hour average: ${fmtKw(peakKw)} kW`,
        `24-hour mean: ${fmtKw(meanKw)} kW`,
        `Based on ${peak.observation_count.toLocaleString("en-GB")} minute observations`,
      ],
      period: datasetPeriod,
    });

    insights.push({
      id: "low-hour",
      type: "low",
      title: `Quietest at ${String(trough.hour).padStart(2, "0")}:00`,
      explanation: `The lowest average draw occurs in the ${String(trough.hour).padStart(2, "0")}:00 hour, ${fmtNum(Math.abs(troughDelta), 1)}% ${troughDelta <= 0 ? "below" : "above"} the 24-hour mean — the best window for load-shifting assessments.`,
      bullets: [
        `Trough hour average: ${fmtKw(troughKw)} kW`,
        `24-hour mean: ${fmtKw(meanKw)} kW`,
        `Based on ${trough.observation_count.toLocaleString("en-GB")} minute observations`,
      ],
      period: datasetPeriod,
    });
  }

  /* ---- Weekday vs weekend ---- */
  const weekday = patterns.weekday;
  if (weekday.length >= 5) {
    const isWeekend = (name: string) => name.startsWith("Sat") || name.startsWith("Sun");
    const weightedMean = (points: typeof weekday) => {
      const total = points.reduce((sum, point) => sum + point.observation_count, 0);
      if (total === 0) return null;
      return (
        points.reduce((sum, point) => sum + point.average_consumption_kwh * point.observation_count, 0) / total
      );
    };
    const weekMean = weightedMean(weekday.filter((point) => !isWeekend(point.day_name)));
    const weekendMean = weightedMean(weekday.filter((point) => isWeekend(point.day_name)));

    if (weekMean !== null && weekendMean !== null) {
      const delta = weekMean !== 0 ? ((weekendMean - weekMean) / weekMean) * 100 : 0;
      const busiestDay = weekday.reduce((best, point) =>
        point.average_consumption_kwh > best.average_consumption_kwh ? point : best,
      );
      insights.push({
        id: "weekday-weekend",
        type: "comparison",
        title:
          delta >= 0
            ? `Weekends draw ${fmtNum(Math.abs(delta), 1)}% more`
            : `Weekends draw ${fmtNum(Math.abs(delta), 1)}% less`,
        explanation: `Observation-weighted weekday and weekend averages differ by ${fmtNum(Math.abs(delta), 1)} percentage points, with ${busiestDay.day_name} the highest-drawing day of the week.`,
        bullets: [
          `Weekday average: ${fmtKw(kW(weekMean))} kW`,
          `Weekend average: ${fmtKw(kW(weekendMean))} kW`,
          `Highest day: ${busiestDay.day_name} at ${fmtKw(kW(busiestDay.average_consumption_kwh))} kW`,
        ],
        period: datasetPeriod,
      });
    }
  }

  /* ---- Monthly seasonality ---- */
  const monthly = patterns.monthly;
  if (monthly.length >= 2) {
    const high = monthly.reduce((best, point) =>
      point.average_consumption_kwh > best.average_consumption_kwh ? point : best,
    );
    const low = monthly.reduce((best, point) =>
      point.average_consumption_kwh < best.average_consumption_kwh ? point : best,
    );
    const highKw = kW(high.average_consumption_kwh);
    const lowKw = kW(low.average_consumption_kwh);
    const spread = lowKw > 0 ? ((highKw - lowKw) / lowKw) * 100 : 0;

    insights.push({
      id: "monthly-pattern",
      type: "pattern",
      title: `${high.month_name} is the heaviest month`,
      explanation: `Monthly averages swing ${fmtNum(spread, 1)}% between ${high.month_name} (${fmtKw(highKw)} kW) and ${low.month_name} (${fmtKw(lowKw)} kW), indicating a clear seasonal load profile.`,
      bullets: [
        `${high.month_name} average: ${fmtKw(highKw)} kW`,
        `${low.month_name} average: ${fmtKw(lowKw)} kW`,
        `Each month aggregates ${monthly.length} calendar months of readings`,
      ],
      period: datasetPeriod,
    });
  }

  /* ---- Recent consumption change (last 30 stored days) ---- */
  const daily = overview.daily_trend;
  if (daily.length >= 14) {
    const complete = daily.filter((point) => point.is_complete);
    const series = complete.length >= 14 ? complete : daily;
    const split = Math.floor(series.length / 2);
    const first = series.slice(0, split);
    const second = series.slice(split);
    const meanOf = (points: typeof series) =>
      points.reduce((sum, point) => sum + point.consumption_kwh, 0) / points.length;

    const firstMean = meanOf(first);
    const secondMean = meanOf(second);
    const change = firstMean !== 0 ? ((secondMean - firstMean) / firstMean) * 100 : 0;
    const period = `${fmtDate(first[0].period_start)} – ${fmtDate(second[second.length - 1].period_start)}`;

    insights.push({
      id: "recent-change",
      type: "change",
      title:
        Math.abs(change) < 1
          ? "Daily demand is holding steady"
          : `Daily demand ${change > 0 ? "rose" : "fell"} ${fmtNum(Math.abs(change), 1)}%`,
      explanation: `Comparing the first ${first.length} days with the most recent ${second.length} days of stored data, the daily average moved from ${fmtNum(firstMean, 1)} kWh to ${fmtNum(secondMean, 1)} kWh${complete.length >= 14 ? " (complete days only)" : ""}.`,
      bullets: [
        `Earlier average: ${fmtNum(firstMean, 1)} kWh/day`,
        `Recent average: ${fmtNum(secondMean, 1)} kWh/day`,
        `Change: ${change >= 0 ? "+" : ""}${fmtNum(change, 1)}%`,
      ],
      period,
    });

    const peakDay = daily.reduce((best, point) =>
      point.consumption_kwh > best.consumption_kwh ? point : best,
    );
    insights.push({
      id: "recent-peak-day",
      type: "peak",
      title: `Highest recent day: ${fmtDate(peakDay.period_start)}`,
      explanation: `Within the last ${daily.length} stored days, ${fmtDate(peakDay.period_start)} recorded the largest daily total at ${fmtNum(peakDay.consumption_kwh, 1)} kWh across ${peakDay.observation_count.toLocaleString("en-GB")} readings${peakDay.is_complete ? "" : " (partial day)"}.`,
      bullets: [
        `Daily total: ${fmtNum(peakDay.consumption_kwh, 1)} kWh`,
        `Observations: ${peakDay.observation_count.toLocaleString("en-GB")}`,
        `Window: last ${daily.length} days`,
      ],
      period: `${fmtDate(daily[0].period_start)} – ${fmtDate(daily[daily.length - 1].period_start)}`,
    });
  }

  /* ---- Anomaly activity ---- */
  const anomaly = overview.anomaly;
  const methods = anomalySummary?.methods ?? [];
  if (anomaly.total_anomalies > 0) {
    insights.push({
      id: "anomaly-activity",
      type: "anomaly",
      title: `${anomaly.total_anomalies.toLocaleString("en-GB")} anomalies flagged`,
      explanation: `The Isolation Forest flagged ${fmtNum(anomaly.anomaly_percentage, 2)}% of ${anomaly.total_observations.toLocaleString("en-GB")} scored observations as statistical deviations. These are detected anomalies, not confirmed faults.`,
      bullets: [
        `Anomaly rate: ${fmtNum(anomaly.anomaly_percentage, 2)}%`,
        `Latest detection: ${fmtDate(anomaly.latest_detected_at)}`,
        methods.length > 0
          ? `Method: ${methods.map((method) => method.detection_method).join(", ")}`
          : "Method: Isolation Forest",
      ],
      period: datasetPeriod,
    });
  } else {
    insights.push({
      id: "anomaly-activity",
      type: "anomaly",
      title: "No anomalies recorded yet",
      explanation:
        "Anomaly detection has not flagged any observation in the stored history. Run detection to populate this insight.",
      bullets: [
        `Scored observations: ${anomaly.total_observations.toLocaleString("en-GB")}`,
        "Flagged observations: 0",
      ],
      period: datasetPeriod,
    });
  }

  /* ---- Optional: header range summary ---- */
  if (rangeLabel && rangeTotals && rangeTotals.observations > 0) {
    insights.push({
      id: "range-summary",
      type: "pattern",
      title: "Selected range summary",
      explanation: `For the date range you selected, the backend reports ${fmtNum(rangeTotals.totalKwh, 1)} kWh across ${rangeTotals.observations.toLocaleString("en-GB")} minute observations.`,
      bullets: [
        `Range total: ${fmtNum(rangeTotals.totalKwh, 1)} kWh`,
        `Observations: ${rangeTotals.observations.toLocaleString("en-GB")}`,
        `Range: ${rangeLabel}`,
      ],
      period: rangeLabel,
    });
  }

  return insights;
}
