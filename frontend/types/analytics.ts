/** Analytics endpoints: overview and consumption patterns. */

import type { EnergyAggregatePoint } from "@/types/energy";

export interface EnergyOverview {
  start_timestamp: string | null;
  end_timestamp: string | null;
  total_observations: number;
  total_consumption_kwh: number;
  average_consumption_kwh: number;
  peak_consumption_kwh: number;
}

export interface ForecastOverview {
  total_predictions: number;
  models: string[];
  latest_forecast_timestamp: string | null;
  latest_generated_at: string | null;
}

export interface AnomalyOverview {
  total_observations: number;
  total_anomalies: number;
  anomaly_percentage: number;
  latest_detected_at: string | null;
}

export interface AnalyticsOverviewResponse {
  energy: EnergyOverview;
  forecast: ForecastOverview;
  anomaly: AnomalyOverview;
  hourly_trend: EnergyAggregatePoint[];
  daily_trend: EnergyAggregatePoint[];
}

export interface HourlyPatternPoint {
  hour: number;
  average_consumption_kwh: number;
  observation_count: number;
}

export interface WeekdayPatternPoint {
  day_of_week: number;
  day_name: string;
  average_consumption_kwh: number;
  observation_count: number;
}

export interface MonthlyPatternPoint {
  month: number;
  month_name: string;
  average_consumption_kwh: number;
  observation_count: number;
}

export interface ConsumptionPatternsResponse {
  hourly: HourlyPatternPoint[];
  weekday: WeekdayPatternPoint[];
  monthly: MonthlyPatternPoint[];
}
