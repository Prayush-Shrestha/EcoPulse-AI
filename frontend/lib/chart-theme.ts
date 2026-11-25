/** Shared Recharts styling: axis, grid and series colours from the theme. */

import type { AxisDomainItem } from "recharts";

export const chartColors = {
  /** Primary energy green: predictions, highlights. */
  primary: "#8bcf9b",
  /** Secondary green: secondary series. */
  accent: "#b6e3a7",
  /** Actual / observed consumption. */
  actual: "#dfe8e0",
  warning: "#e7c88b",
  danger: "#e39a8b",
  muted: "#9ba99d",
  grid: "#2a352d",
  axis: "#6f7d72",
} as const;

export const axisStyle = {
  tick: { fill: chartColors.axis, fontSize: 10, fontFamily: "var(--font-geist-mono)" },
  tickLine: false,
  axisLine: false,
} as const;

export const gridProps = {
  stroke: chartColors.grid,
  strokeDasharray: "3 4",
  vertical: false,
} as const;

/** Hover cursor line shared by every chart tooltip. */
export const tooltipCursor = {
  stroke: chartColors.grid,
  strokeDasharray: "3 4",
} as const;

/**
 * Recharts domain prop accepts a number tuple, a string array or a number
 * array; this alias mirrors the accepted shapes without deep imports.
 */
export type ChartDomain =
  | readonly number[]
  | readonly string[]
  | readonly [AxisDomainItem, AxisDomainItem];
