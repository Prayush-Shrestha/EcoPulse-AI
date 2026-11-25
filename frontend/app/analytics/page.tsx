import type { Metadata } from "next";

import { ConsumptionChart } from "@/components/dashboard/ConsumptionChart";
import {
  AnalyticsKpis,
  DailyDistribution,
  DataExplorer,
  HourPatternChart,
  MonthlyPatternChart,
  PeriodPresets,
  WeekdayPatternChart,
} from "@/app/analytics/panels";

export const metadata: Metadata = {
  title: "Energy Analytics",
};

export default function AnalyticsPage() {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted">
          Aggregated from real minute-level readings in PostgreSQL.
        </p>
        <PeriodPresets />
      </div>

      <AnalyticsKpis />

      <ConsumptionChart />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="min-w-0">
          <HourPatternChart />
        </div>
        <div className="min-w-0">
          <WeekdayPatternChart />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="min-w-0">
          <MonthlyPatternChart />
        </div>
        <div className="min-w-0">
          <DailyDistribution />
        </div>
      </div>

      <DataExplorer />
    </div>
  );
}
