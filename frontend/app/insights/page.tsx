import type { Metadata } from "next";

import { InsightsView } from "@/app/insights/insights-view";

export const metadata: Metadata = {
  title: "Smart Insights",
};

export default function InsightsPage() {
  return <InsightsView />;
}
