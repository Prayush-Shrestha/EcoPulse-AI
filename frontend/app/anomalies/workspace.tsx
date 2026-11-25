"use client";

/** Anomaly monitoring workspace: stats, timeline, filterable table, detail. */

import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Radar, ShieldAlert, Search, X } from "lucide-react";

import { AnomalyChart } from "@/components/dashboard/AnomalyChart";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useAnalyticsOverview } from "@/hooks/useAnalytics";
import { useAnomalyHistory, useAnomalySummary } from "@/hooks/useAnomalies";
import { useEnergyActuals } from "@/hooks/useEnergyData";
import { useModels } from "@/hooks/useModels";
import {
  formatCount,
  formatDateTime,
  formatKw,
  formatKwh,
  formatPercent,
  formatScore,
  perMinuteKwhToKw,
  shiftIsoHours,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";
import type { AnomalyRecord, Severity } from "@/types/anomaly";

const PAGE_SIZE = 15;

const severityTone: Record<Severity, BadgeTone> = {
  none: "neutral",
  low: "info",
  medium: "warning",
  high: "danger",
};

const severityRank: Record<Severity, number> = { none: 0, low: 1, medium: 2, high: 3 };

type SortKey = "timestamp" | "energy" | "score" | "method" | "severity";

export function AnomaliesWorkspace() {
  const [mode, setMode] = useState<"consumption" | "score">("consumption");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("timestamp");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const history = useAnomalyHistory({ limit: 1000 });
  const summary = useAnomalySummary();
  const overview = useAnalyticsOverview();
  const models = useModels();

  const threshold =
    models.data?.models.find((m) => m.key === "anomaly_detection")?.threshold ?? null;

  const rows = useMemo(() => history.data?.items ?? [], [history.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? rows.filter((row) =>
          [
            formatDateTime(row.observation_timestamp),
            row.detection_method,
            row.severity,
            row.is_anomaly ? "anomaly" : "normal",
            formatScore(row.anomaly_score),
          ]
            .join(" ")
            .toLowerCase()
            .includes(needle),
        )
      : rows;

    const sorted = [...matched].sort((a, b) => {
      const direction = sortDir === "asc" ? 1 : -1;
      switch (sortKey) {
        case "timestamp":
          return direction * a.observation_timestamp.localeCompare(b.observation_timestamp);
        case "energy":
          return direction * (a.energy_consumption_kwh - b.energy_consumption_kwh);
        case "score":
          return direction * (a.anomaly_score - b.anomaly_score);
        case "method":
          return direction * a.detection_method.localeCompare(b.detection_method);
        case "severity":
          return direction * (severityRank[a.severity] - severityRank[b.severity]);
      }
    });
    return sorted;
  }, [rows, query, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  const selected = rows.find((row) => row.id === selectedId) ?? null;

  // Summary totals across detection methods (real counts from the API).
  const totals = useMemo(() => {
    const methods = summary.data?.methods ?? [];
    const observations = methods.reduce((sum, method) => sum + method.total_observations, 0);
    const anomalies = methods.reduce((sum, method) => sum + method.total_anomalies, 0);
    return {
      observations,
      anomalies,
      percentage: observations > 0 ? (anomalies / observations) * 100 : 0,
      names: methods.map((method) => method.detection_method),
    };
  }, [summary.data]);

  const anomalyOverview = overview.data?.anomaly;

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((value) => (value === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
    setPage(0);
  };

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          label="Observations analysed"
          value={totals.observations > 0 ? formatCount(totals.observations) : "—"}
          unit="rows"
          icon={Radar}
          loading={summary.loading}
          context="Counted across stored detection runs"
        />
        <MetricCard
          label="Anomalies detected"
          value={summary.data ? formatCount(totals.anomalies) : "—"}
          unit="records"
          icon={ShieldAlert}
          tone={totals.anomalies > 0 ? "warning" : "default"}
          loading={summary.loading}
          context="Detected deviations, not confirmed faults"
        />
        <MetricCard
          label="Anomaly rate"
          value={summary.data ? formatPercent(totals.percentage, 2) : "—"}
          unit="of analysed"
          icon={Radar}
          loading={summary.loading}
          context={`${formatCount(totals.anomalies)} of ${formatCount(totals.observations)} scored observations`}
        />
        <MetricCard
          label="Latest anomaly"
          value={
            anomalyOverview?.latest_detected_at
              ? formatDateTime(anomalyOverview.latest_detected_at).split(" · ")[0]
              : totals.anomalies > 0
                ? "—"
                : "none"
          }
          unit={anomalyOverview?.latest_detected_at ? "date" : ""}
          icon={ShieldAlert}
          loading={overview.loading}
          context={
            anomalyOverview?.latest_detected_at
              ? `Recorded ${formatDateTime(anomalyOverview.latest_detected_at)}`
              : undefined
          }
        />
        <MetricCard
          label="Detection method"
          value={totals.names.length > 0 ? totals.names.join(", ") : "—"}
          unit=""
          icon={Radar}
          loading={summary.loading}
          context={summary.data?.label_status ? "Detections via API — not labelled accuracy" : undefined}
        />
      </div>

      {/* Timeline */}
      <AnomalyChart
        granularity="hourly"
        mode={mode}
        controls={
          <SegmentedControl
            options={[
              { value: "consumption", label: "Consumption" },
              { value: "score", label: "Score" },
            ]}
            value={mode}
            onChange={setMode}
            ariaLabel="Anomaly chart view"
          />
        }
      />

      {/* Table + detail */}
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="min-w-0 xl:col-span-2">
          <Card
            title="Anomaly records"
            subtitle="Scored observations from the Isolation Forest — select a row for detail"
            action={
              <label className="flex items-center gap-2 rounded-lg border border-line bg-canvas px-2.5 py-1.5">
                <Search className="size-3.5 shrink-0 text-muted/70" aria-hidden />
                <input
                  type="search"
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setPage(0);
                  }}
                  placeholder="Search records…"
                  aria-label="Search anomaly records"
                  className="w-36 bg-transparent text-xs text-ink outline-none placeholder:text-muted/60 sm:w-48"
                />
              </label>
            }
            flush
          >
            {history.error && !history.loading ? (
              <div className="p-5">
                <ErrorState error={history.error} onRetry={history.refresh} />
              </div>
            ) : history.loading && rows.length === 0 ? (
              <div className="p-5">
                <ChartSkeleton height={340} />
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title={rows.length === 0 ? "No anomaly records yet" : "No matching records"}
                  description={
                    rows.length === 0
                      ? "Run anomaly detection on the observations you care about; results are persisted and appear here."
                      : "Adjust the search or the header date range."
                  }
                />
              </div>
            ) : (
              <div className="max-h-[520px] overflow-auto">
                <table className="data-table">
                  <thead className="sticky top-0 bg-surface">
                    <tr>
                      <SortHeader label="Timestamp" sortKey="timestamp" active={sortKey} dir={sortDir} onSort={toggleSort} />
                      <SortHeader label="Energy (kWh)" sortKey="energy" active={sortKey} dir={sortDir} onSort={toggleSort} />
                      <SortHeader label="Score" sortKey="score" active={sortKey} dir={sortDir} onSort={toggleSort} />
                      <SortHeader label="Method" sortKey="method" active={sortKey} dir={sortDir} onSort={toggleSort} />
                      <SortHeader label="Status" sortKey="severity" active={sortKey} dir={sortDir} onSort={toggleSort} />
                      <th scope="col">Severity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.map((row) => (
                      <tr
                        key={row.id}
                        onClick={() => setSelectedId(row.id === selectedId ? null : row.id)}
                        className={cn(
                          "cursor-pointer",
                          selectedId === row.id && "bg-primary/10",
                        )}
                      >
                        <td className="whitespace-nowrap font-mono text-[11px]">
                          {formatDateTime(row.observation_timestamp)}
                        </td>
                        <td className="font-mono">{formatKwh(row.energy_consumption_kwh, 4)}</td>
                        <td
                          className={cn(
                            "font-mono",
                            row.is_anomaly ? "text-danger" : "text-muted",
                          )}
                        >
                          {formatScore(row.anomaly_score)}
                        </td>
                        <td className="whitespace-nowrap text-muted">{row.detection_method}</td>
                        <td>
                          <Badge tone={row.is_anomaly ? "danger" : "neutral"}>
                            {row.is_anomaly ? "anomaly" : "normal"}
                          </Badge>
                        </td>
                        <td>
                          <Badge tone={severityTone[row.severity]}>{row.severity}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {filtered.length > 0 ? (
              <div className="flex items-center justify-between gap-3 border-t border-line/60 px-5 py-3">
                <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
                  {formatCount(filtered.length)} records
                  {query ? ` matching “${query}”` : ""}
                  {history.data && history.data.total > rows.length
                    ? ` · showing first ${formatCount(rows.length)} of ${formatCount(history.data.total)}`
                    : ""}
                  {" · "}page {safePage + 1} of {pageCount}
                </p>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setPage(Math.max(0, safePage - 1))}
                    disabled={safePage === 0}
                    aria-label="Previous page"
                    className="grid size-7 place-items-center rounded-md border border-line text-muted transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  >
                    <ArrowUp className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage(Math.min(pageCount - 1, safePage + 1))}
                    disabled={safePage >= pageCount - 1}
                    aria-label="Next page"
                    className="grid size-7 place-items-center rounded-md border border-line text-muted transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  >
                    <ArrowDown className="size-3.5" />
                  </button>
                </div>
              </div>
            ) : null}
          </Card>
        </div>

        <div className="min-w-0">
          <AnomalyDetail record={selected} threshold={threshold} onClose={() => setSelectedId(null)} />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Sortable header                                                     */
/* ------------------------------------------------------------------ */

function SortHeader({
  label,
  sortKey,
  active,
  dir,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  active: SortKey;
  dir: "asc" | "desc";
  onSort: (key: SortKey) => void;
}) {
  const isActive = active === sortKey;
  return (
    <th
      scope="col"
      aria-sort={isActive ? (dir === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="inline-flex items-center gap-1 uppercase tracking-[0.1em] transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        {label}
        {isActive ? (
          dir === "asc" ? (
            <ArrowUp className="size-3 text-primary" aria-hidden />
          ) : (
            <ArrowDown className="size-3 text-primary" aria-hidden />
          )
        ) : null}
      </button>
    </th>
  );
}

/* ------------------------------------------------------------------ */
/* Detail panel                                                        */
/* ------------------------------------------------------------------ */

function AnomalyDetail({
  record,
  threshold,
  onClose,
}: {
  record: AnomalyRecord | null;
  threshold: number | null;
  onClose: () => void;
}) {
  const contextStart = record ? shiftIsoHours(record.observation_timestamp, -3) : undefined;
  const contextEnd = record ? shiftIsoHours(record.observation_timestamp, 3) : undefined;
  const context = useEnergyActuals(contextStart, contextEnd, "hourly");

  if (!record) {
    return (
      <Card title="Anomaly detail" subtitle="Select a record from the table">
        <EmptyState
          title="Nothing selected"
          description="Pick a row to inspect its score, surrounding consumption and why it was flagged."
          className="min-h-0 py-8"
        />
      </Card>
    );
  }

  const readingKw = perMinuteKwhToKw(record.energy_consumption_kwh);

  // Average kW across surrounding hours, excluding the observation's own hour.
  const ownHour = `${record.observation_timestamp.slice(0, 13)}:00:00`;
  const surrounding = (context.data?.items ?? []).filter(
    (point) => point.period_start !== ownHour,
  );
  const contextAvgKw =
    surrounding.length > 0
      ? surrounding.reduce((sum, point) => sum + point.consumption_kwh, 0) / surrounding.length
      : null;
  const deltaPct =
    contextAvgKw !== null && contextAvgKw !== 0
      ? ((readingKw - contextAvgKw) / contextAvgKw) * 100
      : null;

  const flagged = record.is_anomaly;
  const belowThreshold = threshold !== null && record.anomaly_score < threshold;

  return (
    <Card
      title="Anomaly detail"
      subtitle={formatDateTime(record.observation_timestamp)}
      action={
        <button
          type="button"
          onClick={onClose}
          aria-label="Close detail"
          className="grid size-7 place-items-center rounded-md border border-line text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          <X className="size-3.5" />
        </button>
      }
    >
      <div className="flex items-center gap-2">
        <Badge tone={flagged ? "danger" : "neutral"}>
          {flagged ? "detected anomaly" : "within expected range"}
        </Badge>
        <Badge tone={severityTone[record.severity]}>{record.severity}</Badge>
      </div>

      <dl className="mt-4 space-y-3 text-xs">
        <DetailRow label="Energy reading">
          <span className="font-mono">
            {formatKwh(record.energy_consumption_kwh, 4)} kWh/min · {formatKw(readingKw)} kW
          </span>
        </DetailRow>
        <DetailRow label="Anomaly score">
          <span className={cn("font-mono", flagged ? "text-danger" : "text-ink")}>
            {formatScore(record.anomaly_score)}
          </span>
        </DetailRow>
        <DetailRow label="Detection method">
          <span className="font-mono">{record.detection_method}</span>
        </DetailRow>
        <DetailRow label="Recorded at">
          <span className="font-mono">{formatDateTime(record.detected_at)}</span>
        </DetailRow>
        <DetailRow label="Surrounding hours">
          {context.loading ? (
            <span className="text-muted">loading…</span>
          ) : contextAvgKw !== null ? (
            <span className="font-mono">
              {formatKw(contextAvgKw)} kW avg
              {deltaPct !== null
                ? ` · reading ${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(1)}%`
                : ""}
            </span>
          ) : (
            <span className="text-muted">no neighbouring hours in range</span>
          )}
        </DetailRow>
      </dl>

      <div className="mt-4 rounded-lg border border-line/70 bg-canvas/60 px-3.5 py-3">
        <p className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
          <ShieldAlert className="size-3" aria-hidden />
          Why it was flagged
        </p>
        <p className="mt-1.5 text-[11px] leading-5 text-muted">
          {flagged ? (
            <>
              The Isolation Forest scored this minute{" "}
              <span className="font-mono text-ink">{formatScore(record.anomaly_score)}</span>
              {threshold !== null ? (
                <>
                  , which is {belowThreshold ? "below" : "not below"} the model decision
                  threshold of <span className="font-mono text-ink">{formatScore(threshold)}</span>
                </>
              ) : null}
              {", so it was flagged as an anomaly. "}
              Severity “{record.severity}” is a heuristic ranking of the score, not a
              calibrated fault severity.
            </>
          ) : (
            <>
              The score sits at or above the model decision threshold
              {threshold !== null ? (
                <>
                  {" "}
                  (<span className="font-mono text-ink">{formatScore(threshold)}</span>)
                </>
              ) : null}
              , so the observation was recorded as within the expected range.
            </>
          )}
        </p>
        <p className="mt-2 border-t border-line/50 pt-2 text-[10px] text-muted/70">
          Detected anomalies, not confirmed faults — no label data exists to confirm
          real-world events.
        </p>
      </div>

      {context.error ? (
        <p className="mt-3 text-[11px] text-warning">
          Surrounding-context request failed: {context.error.message}
        </p>
      ) : null}
    </Card>
  );
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 text-right text-ink">{children}</dd>
    </div>
  );
}
