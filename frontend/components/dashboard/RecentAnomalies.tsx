"use client";

import Link from "next/link";
import { ArrowUpRight, ShieldAlert } from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useAnomalyHistory } from "@/hooks/useAnomalies";
import { formatDateTime, formatKwh, formatScore } from "@/lib/formatters";
import type { Severity } from "@/types/anomaly";

const severityTone: Record<Severity, BadgeTone> = {
  none: "neutral",
  low: "info",
  medium: "warning",
  high: "danger",
};

interface RecentAnomaliesProps {
  limit?: number;
}

/** Compact list of the most recent detected anomalies. */
export function RecentAnomalies({ limit = 6 }: RecentAnomaliesProps) {
  const { data, loading, error, refresh } = useAnomalyHistory({
    is_anomaly: true,
    limit,
  });

  const items = data?.items ?? [];

  return (
    <Card
      title="Recent anomalies"
      subtitle="Latest detected deviations · not confirmed faults"
      action={
        <Link
          href="/anomalies"
          className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted transition-colors hover:text-ink"
        >
          View all
          <ArrowUpRight className="size-3" aria-hidden />
        </Link>
      }
    >
      {error && !loading ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : loading ? (
        <ChartSkeleton height={190} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No anomalies recorded"
          description="Run anomaly detection or wait for stored results to appear."
          className="min-h-0 py-6"
        />
      ) : (
        <ul className="divide-y divide-line/50">
          {items.map((record) => (
            <li key={record.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
              <span
                className={`grid size-7 shrink-0 place-items-center rounded-md border ${
                  record.severity === "high"
                    ? "border-danger/30 bg-danger/10 text-danger"
                    : record.severity === "medium"
                      ? "border-warning/30 bg-warning/10 text-warning"
                      : "border-line bg-canvas text-muted"
                }`}
                aria-hidden
              >
                <ShieldAlert className="size-3.5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-ink">
                  {formatDateTime(record.observation_timestamp)}
                </p>
                <p className="font-mono text-[10px] text-muted">
                  {formatKwh(record.energy_consumption_kwh)} kWh · score{" "}
                  {formatScore(record.anomaly_score)}
                </p>
              </div>
              <Badge tone={severityTone[record.severity]}>{record.severity}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
