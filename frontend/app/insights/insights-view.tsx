"use client";

/** Insights view: renders rule-based insights from real backend analytics. */

import { useMemo } from "react";
import { Lightbulb, Info } from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useAnalyticsOverview, useConsumptionPatterns } from "@/hooks/useAnalytics";
import { useAnomalySummary } from "@/hooks/useAnomalies";
import { useEnergySummary } from "@/hooks/useEnergyData";
import { useApp } from "@/lib/app-context";
import { formatDate } from "@/lib/formatters";
import { buildInsights, TYPE_LABELS, type InsightType } from "@/app/insights/rules";

const typeTone: Record<InsightType, BadgeTone> = {
  peak: "warning",
  low: "ok",
  pattern: "info",
  comparison: "info",
  change: "neutral",
  anomaly: "danger",
};

export function InsightsView() {
  const overview = useAnalyticsOverview();
  const patterns = useConsumptionPatterns();
  const anomalySummary = useAnomalySummary();
  const summary = useEnergySummary();
  const { range } = useApp();

  const rangeLabel =
    range.start || range.end
      ? `${formatDate(range.start ? `${range.start}T00:00:00` : null)} – ${formatDate(range.end ? `${range.end}T00:00:00` : null)}`
      : undefined;

  const insights = useMemo(() => {
    if (!overview.data || !patterns.data) return [];
    return buildInsights({
      overview: overview.data,
      patterns: patterns.data,
      anomalySummary: anomalySummary.data,
      rangeLabel,
      rangeTotals: summary.data
        ? {
            totalKwh: summary.data.total_consumption_kwh,
            observations: summary.data.total_observations,
          }
        : null,
    });
  }, [overview.data, patterns.data, anomalySummary.data, rangeLabel, summary.data]);

  const loading =
    (overview.loading && !overview.data) || (patterns.loading && !patterns.data);
  const error = overview.error ?? patterns.error;

  return (
    <div className="space-y-4">
      <Card
        title="How these insights are produced"
        subtitle="Deterministic rules over backend analytics — no language model involved"
        action={<Badge tone="info">explainable rules</Badge>}
      >
        <div className="flex items-start gap-3 text-xs leading-5 text-muted">
          <Info className="mt-0.5 size-4 shrink-0 text-muted/70" aria-hidden />
          <p>
            Each insight states the rule it applied and the exact numbers it used. Inputs come
            from <span className="text-ink">GET /analytics/consumption-patterns</span>,{" "}
            <span className="text-ink">GET /analytics/overview</span> and{" "}
            <span className="text-ink">GET /anomalies/summary</span>. Percentages are computed
            from those responses — nothing is estimated or invented.
          </p>
        </div>
      </Card>

      {error && !loading ? (
        <ErrorState
          error={error}
          onRetry={() => {
            overview.refresh();
            patterns.refresh();
            anomalySummary.refresh();
          }}
        />
      ) : loading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="panel p-5">
              <ChartSkeleton height={140} />
            </div>
          ))}
        </div>
      ) : insights.length === 0 ? (
        <EmptyState
          title="No insights available"
          description="The backend returned no analytics to derive insights from."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {insights.map((insight) => (
            <article key={insight.id} className="panel flex min-w-0 flex-col p-5">
              <div className="flex items-start justify-between gap-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
                  <Lightbulb className="size-4" aria-hidden />
                </span>
                <Badge tone={typeTone[insight.type]}>{TYPE_LABELS[insight.type]}</Badge>
              </div>

              <h2 className="mt-3 text-sm font-medium tracking-[-0.01em] text-ink">
                {insight.title}
              </h2>
              <p className="mt-1.5 text-xs leading-5 text-muted">{insight.explanation}</p>

              <ul className="mt-3 space-y-1.5 border-t border-line/50 pt-3">
                {insight.bullets.map((bullet) => (
                  <li key={bullet} className="flex items-start gap-2 text-[11px] text-ink/90">
                    <span
                      className="mt-1.5 size-1 shrink-0 rounded-full bg-primary/70"
                      aria-hidden
                    />
                    <span className="font-mono">{bullet}</span>
                  </li>
                ))}
              </ul>

              <p className="mt-auto pt-3 font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
                Period: {insight.period}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
