"use client";

import type { ReactNode } from "react";

import { chartColors } from "@/lib/chart-theme";

interface TooltipEntry {
  value?: number | string;
  name?: string | number | string[];
  color?: string;
  payload?: Record<string, unknown>;
}

export interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: ReactNode;
  /** Formats the x-axis label shown as the tooltip title. */
  labelFormatter?: (label: ReactNode, payload?: unknown) => ReactNode;
  /** Formats one series value (already receives the raw number). */
  valueFormatter?: (value: number, name: string) => string;
}

function formatValue(
  value: number,
  name: string,
  formatter?: ChartTooltipProps["valueFormatter"],
): string {
  if (formatter) return formatter(value, name);
  return value.toLocaleString("en-GB", { maximumFractionDigits: 3 });
}

/**
 * Shared tooltip body for every chart. Passed to Recharts through the
 * `content` prop (an element), so all tooltips share one visual contract.
 */
export function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
  valueFormatter,
}: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const title =
    label !== undefined && label !== null
      ? labelFormatter
        ? labelFormatter(label)
        : String(label)
      : null;

  return (
    <div className="min-w-[150px] rounded-lg border border-line bg-surface px-3 py-2.5 shadow-[0_18px_40px_-24px_rgba(0,0,0,0.9)]">
      {title !== null ? (
        <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted">{title}</p>
      ) : null}
      <ul className="mt-1.5 space-y-1">
        {payload.map((entry, index) => {
          const name = Array.isArray(entry.name)
            ? entry.name.join(", ")
            : String(entry.name ?? "");
          const numeric =
            typeof entry.value === "number" ? entry.value : Number(entry.value);
          return (
            <li
              key={`${name}-${index}`}
              className="flex items-center justify-between gap-4 text-xs"
            >
              <span className="flex items-center gap-2 text-muted">
                <span
                  className="size-1.5 rounded-full"
                  style={{ backgroundColor: entry.color ?? chartColors.primary }}
                  aria-hidden
                />
                {name}
              </span>
              <span className="font-mono text-[11px] text-ink">
                {Number.isFinite(numeric)
                  ? formatValue(numeric, name, valueFormatter)
                  : "—"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
