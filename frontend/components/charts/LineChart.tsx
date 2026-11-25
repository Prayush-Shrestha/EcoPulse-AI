"use client";

import type { ReactNode } from "react";
import {
  CartesianGrid,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartShell } from "@/components/charts/ChartShell";
import { ChartTooltip, type ChartTooltipProps } from "@/components/charts/ChartTooltip";
import {
  axisStyle,
  gridProps,
  tooltipCursor,
  type ChartDomain,
} from "@/lib/chart-theme";

export interface LineSeriesConfig {
  dataKey: string;
  name: string;
  color: string;
  dashed?: boolean;
  strokeWidth?: number;
  showDot?: boolean;
}

interface LineChartProps<T extends Record<string, unknown>> {
  data: T[];
  xKey: string;
  series: LineSeriesConfig[];
  height?: number;
  loading?: boolean;
  emptyMessage?: string;
  xTickFormatter?: (value: string) => string;
  yTickFormatter?: (value: number) => string;
  yDomain?: ChartDomain;
  tooltipLabelFormatter?: ChartTooltipProps["labelFormatter"];
  tooltipValueFormatter?: ChartTooltipProps["valueFormatter"];
  /** Overlay children such as ReferenceLine or scatter markers. */
  children?: ReactNode;
}

/** Multi-series line chart with consistent axes, grid and tooltip. */
export function LineChart<T extends Record<string, unknown>>({
  data,
  xKey,
  series,
  height = 280,
  loading = false,
  emptyMessage,
  xTickFormatter,
  yTickFormatter,
  yDomain,
  tooltipLabelFormatter,
  tooltipValueFormatter,
  children,
}: LineChartProps<T>) {
  return (
    <ChartShell loading={loading} empty={data.length === 0} height={height} emptyMessage={emptyMessage}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsLineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis
            dataKey={xKey}
            {...axisStyle}
            minTickGap={28}
            tickFormatter={xTickFormatter}
          />
          <YAxis
            {...axisStyle}
            width={52}
            tickFormatter={yTickFormatter}
            domain={yDomain ?? ["auto", "auto"]}
          />
          <Tooltip
            content={
              <ChartTooltip
                labelFormatter={tooltipLabelFormatter}
                valueFormatter={tooltipValueFormatter}
              />
            }
            cursor={tooltipCursor}
          />
          {series.map((config) => (
            <Line
              key={config.dataKey}
              type="monotone"
              dataKey={config.dataKey}
              name={config.name}
              stroke={config.color}
              strokeWidth={config.strokeWidth ?? 1.8}
              strokeDasharray={config.dashed ? "5 4" : undefined}
              dot={config.showDot ? { r: 2, fill: config.color, strokeWidth: 0 } : false}
              activeDot={{ r: 3.5, strokeWidth: 0 }}
              isAnimationActive={false}
              connectNulls
            />
          ))}
          {children}
        </RechartsLineChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}
