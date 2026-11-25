"use client";

import {
  Area,
  AreaChart as RechartsAreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartShell } from "@/components/charts/ChartShell";
import { ChartTooltip, type ChartTooltipProps } from "@/components/charts/ChartTooltip";
import {
  axisStyle,
  chartColors,
  gridProps,
  tooltipCursor,
  type ChartDomain,
} from "@/lib/chart-theme";

interface AreaChartProps<T extends Record<string, unknown>> {
  data: T[];
  xKey: string;
  valueKey: string;
  name?: string;
  color?: string;
  height?: number;
  loading?: boolean;
  emptyMessage?: string;
  xTickFormatter?: (value: string) => string;
  yTickFormatter?: (value: number) => string;
  yDomain?: ChartDomain;
  tooltipLabelFormatter?: ChartTooltipProps["labelFormatter"];
  tooltipValueFormatter?: ChartTooltipProps["valueFormatter"];
}

/** Single-series area chart used for consumption trends. */
export function AreaChart<T extends Record<string, unknown>>({
  data,
  xKey,
  valueKey,
  name = "Consumption",
  color = chartColors.primary,
  height = 280,
  loading = false,
  emptyMessage,
  xTickFormatter,
  yTickFormatter,
  yDomain,
  tooltipLabelFormatter,
  tooltipValueFormatter,
}: AreaChartProps<T>) {
  return (
    <ChartShell loading={loading} empty={data.length === 0} height={height} emptyMessage={emptyMessage}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsAreaChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <defs>
            <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.28} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey={xKey} {...axisStyle} minTickGap={28} tickFormatter={xTickFormatter} />
          <YAxis
            {...axisStyle}
            width={52}
            tickFormatter={yTickFormatter}
            domain={yDomain ?? [0, "auto"]}
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
          <Area
            type="monotone"
            dataKey={valueKey}
            name={name}
            stroke={color}
            strokeWidth={1.8}
            fill="url(#areaFill)"
            isAnimationActive={false}
            activeDot={{ r: 3.5, strokeWidth: 0 }}
          />
        </RechartsAreaChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}
