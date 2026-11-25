/** Energy endpoints: readings, summary and clock aggregates. */

import type { Pagination } from "@/types/common";

export interface EnergyReading {
  id: number;
  timestamp: string;
  global_active_power: number;
  global_reactive_power: number;
  voltage: number;
  global_intensity: number;
  sub_metering_1: number;
  sub_metering_2: number;
  sub_metering_3: number;
  energy_consumption_kwh: number;
  is_imputed: boolean;
}

export interface EnergyListResponse extends Pagination {
  items: EnergyReading[];
}

export interface EnergySummaryResponse {
  start_timestamp: string | null;
  end_timestamp: string | null;
  total_observations: number;
  total_consumption_kwh: number;
  average_consumption_kwh: number;
  maximum_consumption_kwh: number;
  minimum_consumption_kwh: number;
  units: "kWh";
}

export interface EnergyAggregatePoint {
  period_start: string;
  consumption_kwh: number;
  observation_count: number;
  expected_observations: number;
  is_complete: boolean;
}

export interface EnergyAggregateResponse extends Pagination {
  granularity: "hourly" | "daily" | "monthly";
  items: EnergyAggregatePoint[];
}
