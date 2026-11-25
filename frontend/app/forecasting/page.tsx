import type { Metadata } from "next";

import { ForecastWorkspace } from "@/app/forecasting/workspace";

export const metadata: Metadata = {
  title: "Forecasting",
};

export default function ForecastingPage() {
  return <ForecastWorkspace />;
}
