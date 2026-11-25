"use client";

import { Database, Server, Cpu, HardDrive } from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ChartSkeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/States";
import { useHealth } from "@/hooks/useHealth";
import { formatDateTime } from "@/lib/formatters";
import type { CheckStatus } from "@/types/health";

const checkTone: Record<CheckStatus, BadgeTone> = {
  ok: "ok",
  unavailable: "danger",
};

const checkIcons: Record<string, typeof Database> = {
  database: Database,
  models: Cpu,
  model: Cpu,
  storage: HardDrive,
};

function labelFor(key: string): string {
  return key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** Backend health: overall status plus per-dependency checks. */
export function SystemStatus() {
  const { data, error, checking, checkedAt, refresh } = useHealth();

  return (
    <Card
      title="System status"
      subtitle={
        checkedAt
          ? `Checked ${checkedAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
          : "Polling the FastAPI health endpoint"
      }
      action={
        data ? (
          <Badge tone={data.status === "ok" ? "ok" : "warning"} dot>
            {data.status}
          </Badge>
        ) : error ? (
          <Badge tone="danger" dot>
            offline
          </Badge>
        ) : undefined
      }
    >
      {error && !checking && !data ? (
        <ErrorState error={error} onRetry={refresh} title="Backend unreachable" />
      ) : !data ? (
        <ChartSkeleton height={130} />
      ) : (
        <>
          <ul className="space-y-2.5">
            {Object.entries(data.checks).map(([key, check]) => {
              const Icon = checkIcons[key] ?? Server;
              return (
                <li key={key} className="flex items-center gap-3">
                  <span
                    className={`grid size-7 shrink-0 place-items-center rounded-md border ${
                      check.status === "ok"
                        ? "border-primary/25 bg-primary/10 text-primary"
                        : "border-danger/25 bg-danger/10 text-danger"
                    }`}
                    aria-hidden
                  >
                    <Icon className="size-3.5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs text-ink">{labelFor(key)}</p>
                    {check.detail ? (
                      <p className="truncate text-[10px] text-muted/80">{check.detail}</p>
                    ) : null}
                  </div>
                  {check.latency_ms !== null ? (
                    <span className="font-mono text-[10px] text-muted">
                      {check.latency_ms} ms
                    </span>
                  ) : null}
                  <Badge tone={checkTone[check.status]}>{check.status}</Badge>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 border-t border-line/50 pt-2.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted/70">
            {data.service} v{data.version} · {data.environment} ·{" "}
            {formatDateTime(data.timestamp)}
          </p>
        </>
      )}
    </Card>
  );
}
