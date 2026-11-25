import type { Metadata } from "next";

import { AnomaliesWorkspace } from "@/app/anomalies/workspace";

export const metadata: Metadata = {
  title: "Anomaly Monitoring",
};

export default function AnomaliesPage() {
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">
        Results are <span className="text-warning">detected anomalies, not confirmed faults</span>{" "}
        — the model flags statistical deviations in consumption.
      </p>
      <AnomaliesWorkspace />
    </div>
  );
}
