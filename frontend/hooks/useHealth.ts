"use client";

/** Polled backend health status used by the header badge and settings page. */

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import type { HealthResponse } from "@/types/health";

const HEALTH_POLL_MS = 30_000;

export interface HealthState {
  data: HealthResponse | null;
  error: Error | null;
  /** True only while the very first check is in flight. */
  checking: boolean;
  checkedAt: Date | null;
  refresh: () => void;
}

export function useHealth(pollMs: number = HEALTH_POLL_MS): HealthState {
  const { refreshKey } = useApp();
  const [data, setData] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [checking, setChecking] = useState(true);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [token, setToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    api
      .health(controller.signal)
      .then((value) => {
        if (!active) return;
        setData(value);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!active || controller.signal.aborted) return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (!active) return;
        setChecking(false);
        setCheckedAt(new Date());
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [token, refreshKey]);

  useEffect(() => {
    if (pollMs <= 0) return;
    const interval = window.setInterval(() => setToken((value) => value + 1), pollMs);
    return () => window.clearInterval(interval);
  }, [pollMs]);

  return {
    data,
    error,
    checking,
    checkedAt,
    refresh: () => setToken((value) => value + 1),
  };
}
