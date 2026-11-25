/** Forecast endpoints: generation, history and latest point. */

import type { Pagination } from "@/types/common";

/** Horizons accepted by POST /api/v1/forecasts/predict. */
export const SUPPORTED_HORIZONS = [1, 6, 24, 48] as const;
export type HorizonHours = (typeof SUPPORTED_HORIZONS)[number];

export interface ForecastPoint {
  forecast_timestamp: string;
  predicted_energy_kwh: number;
  model_name: string;
  model_version: string;
  forecast_horizon: number;
  units: "kWh";
}

export interface ForecastResponse {
  generated_at: string;
  base_timestamp: string;
  horizon_hours: number;
  model_name: string;
  model_version: string;
  units: "kWh";
  items: ForecastPoint[];
}

export interface ForecastRecord {
  id: number;
  created_at: string;
  forecast_timestamp: string;
  predicted_energy_kwh: number;
  model_name: string;
  model_version: string;
  forecast_horizon: number;
  units: "kWh";
}

export interface ForecastHistoryResponse extends Pagination {
  items: ForecastRecord[];
}
