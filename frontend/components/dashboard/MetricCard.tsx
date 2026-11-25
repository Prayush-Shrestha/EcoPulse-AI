"use client";

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { KpiSkeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  unit?: string;
  /** Supporting context line (coverage window, comparison, status). */
  context?: ReactNode;
  icon: LucideIcon;
  tone?: "default" | "warning" | "danger";
  loading?: boolean;
}

const iconTones = {
  default: "border-primary/20 bg-primary/10 text-primary",
  warning: "border-warning/20 bg-warning/10 text-warning",
  danger: "border-danger/20 bg-danger/10 text-danger",
} as const;

/** KPI card used on the overview and analytics pages. */
export function MetricCard({
  label,
  value,
  unit,
  context,
  icon: Icon,
  tone = "default",
  loading = false,
}: MetricCardProps) {
  if (loading) {
    return <KpiSkeleton />;
  }

  return (
    <article className="panel flex min-w-0 flex-col gap-3 p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          {label}
        </p>
        <span
          className={cn(
            "grid size-8 shrink-0 place-items-center rounded-lg border",
            iconTones[tone],
          )}
          aria-hidden
        >
          <Icon className="size-4" />
        </span>
      </div>
      <div className="flex min-w-0 items-baseline gap-1.5">
        <span className="truncate text-[26px] font-medium leading-none tracking-[-0.03em] text-ink">
          {value}
        </span>
        {unit ? (
          <span className="shrink-0 font-mono text-[11px] uppercase text-muted">
            {unit}
          </span>
        ) : null}
      </div>
      {context ? (
        <p className="text-[11px] leading-4 text-muted/90">{context}</p>
      ) : null}
    </article>
  );
}
