/** Anomaly endpoints: detection, history and summary. */

import type { Pagination } from "@/types/common";

export type Severity = "none" | "low" | "medium" | "high";

export interface AnomalyRecord {
  id: number;
  detected_at: string;
  observation_timestamp: string;
  energy_consumption_kwh: number;
  anomaly_score: number;
  detection_method: string;
  severity: Severity;
  is_anomaly: boolean;
}

export interface AnomalyHistoryResponse extends Pagination {
  items: AnomalyRecord[];
}

export interface AnomalyMethodSummary {
  detection_method: string;
  total_observations: number;
  total_anomalies: number;
  anomaly_percentage: number;
  start_timestamp: string | null;
  end_timestamp: string | null;
}

export interface AnomalySummaryResponse {
  methods: AnomalyMethodSummary[];
  label_status: string;
}

export interface AnomalyDetectionResponse {
  id: number;
  detected_at: string;
  observation_timestamp: string;
  energy_consumption_kwh: number;
  anomaly_score: number;
  detection_method: string;
  severity: Severity;
  is_anomaly: boolean;
  threshold: number;
  model_name: string;
  model_version: string;
  label_status: string;
}
