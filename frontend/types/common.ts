/** Shared API envelope types mirroring the FastAPI Pydantic schemas. */

export interface Pagination {
  total: number;
  limit: number;
  offset: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown;
  };
}

export type Granularity = "hourly" | "daily" | "monthly";
