"use client";

import {
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  Cell,
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

export interface BarSeriesConfig {
  dataKey: string;
  name: string;
  color?: string;
}

interface BarChartProps<T extends Record<string, unknown>> {
  data: T[];
  xKey: string;
  series: BarSeriesConfig[];
  height?: number;
  loading?: boolean;
  emptyMessage?: string;
  /** Per-bar colour override (e.g. highlight the peak bar). */
  barColor?: (row: T, index: number) => string | undefined;
  radius?: number;
  layout?: "horizontal" | "vertical";
  xTickFormatter?: (value: string) => string;
  yTickFormatter?: (value: number) => string;
  yDomain?: ChartDomain;
  tooltipLabelFormatter?: ChartTooltipProps["labelFormatter"];
  tooltipValueFormatter?: ChartTooltipProps["valueFormatter"];
}

/** Bar chart for patterns, daily summaries and distributions. */
export function BarChart<T extends Record<string, unknown>>({
  data,
  xKey,
  series,
  height = 260,
  loading = false,
  emptyMessage,
  barColor,
  radius = 3,
  layout = "horizontal",
  xTickFormatter,
  yTickFormatter,
  yDomain,
  tooltipLabelFormatter,
  tooltipValueFormatter,
}: BarChartProps<T>) {
  const horizontal = layout === "horizontal";

  return (
    <ChartShell loading={loading} empty={data.length === 0} height={height} emptyMessage={emptyMessage}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsBarChart
          data={data}
          layout={layout}
          margin={{ top: 8, right: 8, bottom: 4, left: 0 }}
          barCategoryGap="22%"
        >
          <CartesianGrid {...gridProps} horizontal={horizontal} vertical={!horizontal} />
          {horizontal ? (
            <>
              <XAxis dataKey={xKey} {...axisStyle} minTickGap={20} tickFormatter={xTickFormatter} />
              <YAxis {...axisStyle} width={52} tickFormatter={yTickFormatter} domain={yDomain ?? [0, "auto"]} />
            </>
          ) : (
            <>
              <XAxis
                dataKey={xKey}
                type="number"
                {...axisStyle}
                tickFormatter={yTickFormatter}
                domain={yDomain ?? [0, "auto"]}
              />
              <YAxis dataKey={xKey} type="category" {...axisStyle} width={72} tickFormatter={xTickFormatter} />
            </>
          )}
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
            <Bar
              key={config.dataKey}
              dataKey={config.dataKey}
              name={config.name}
              fill={config.color ?? chartColors.primary}
              radius={[radius, radius, 0, 0]}
              isAnimationActive={false}
            >
              {barColor
                ? data.map((row, index) => (
                    <Cell
                      key={index}
                      fill={barColor(row, index) ?? config.color ?? chartColors.primary}
                    />
                  ))
                : null}
            </Bar>
          ))}
        </RechartsBarChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}
