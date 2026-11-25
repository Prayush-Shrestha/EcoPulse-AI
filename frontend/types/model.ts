/** Model metadata endpoints: loaded Phase 4 artefacts. */

export interface ModelInfo {
  key: "forecasting" | "anomaly_detection";
  name: string;
  version: string | null;
  status: "loaded" | "unavailable";
  model_type: string | null;
  target: string | null;
  feature_count: number | null;
  trained_at_utc: string | null;
  metrics: Record<string, number> | null;
  threshold: number | null;
  raw_offset: number | null;
  detail: string | null;
}

export interface ModelListResponse {
  models: ModelInfo[];
  label_status: string | null;
}
