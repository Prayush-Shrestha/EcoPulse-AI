import type { Metadata } from "next";

import { AnomalyChart } from "@/components/dashboard/AnomalyChart";
import { ConsumptionChart } from "@/components/dashboard/ConsumptionChart";
import { DailySummary } from "@/components/dashboard/DailySummary";
import { EnergyBreakdown } from "@/components/dashboard/EnergyBreakdown";
import { ForecastSummary } from "@/components/dashboard/ForecastSummary";
import { OverviewKpis } from "@/components/dashboard/OverviewKpis";
import { RecentAnomalies } from "@/components/dashboard/RecentAnomalies";
import { SystemStatus } from "@/components/dashboard/SystemStatus";

export const metadata: Metadata = {
  title: "Overview",
};

export default function OverviewPage() {
  return (
    <div className="space-y-4">
      <OverviewKpis />

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="min-w-0 xl:col-span-2">
          <ConsumptionChart />
        </div>
        <div className="min-w-0">
          <ForecastSummary />
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="min-w-0 xl:col-span-2">
          <AnomalyChart granularity="hourly" mode="consumption" />
        </div>
        <div className="min-w-0">
          <RecentAnomalies />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <div className="min-w-0">
          <EnergyBreakdown />
        </div>
        <div className="min-w-0">
          <DailySummary />
        </div>
        <div className="min-w-0">
          <SystemStatus />
        </div>
      </div>
    </div>
  );
}
