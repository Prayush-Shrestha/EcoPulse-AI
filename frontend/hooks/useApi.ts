"use client";

/**
 * Generic data-fetching hook with loading, error and refresh states.
 *
 * - Aborts in-flight requests when dependencies change or the component unmounts.
 * - Ignores stale responses that resolve after a newer request started.
 * - Refetches when the app-wide refresh token changes (header refresh button).
 * - Keeps the previous data visible during a refresh so charts do not flash.
 */

import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";

import { useApp } from "@/lib/app-context";

export interface UseApiResult<T> {
  data: T | null;
  error: Error | null;
  /** True only before the first successful load. */
  loading: boolean;
  /** True while a refresh is running on top of already-loaded data. */
  refreshing: boolean;
  /** Refetch immediately, bypassing any cached response. */
  refresh: () => void;
}

type Fetcher<T> = (signal: AbortSignal) => Promise<T>;

export function useApi<T>(fetcher: Fetcher<T>, deps: DependencyList): UseApiResult<T> {
  const { refreshKey } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [localRefresh, setLocalRefresh] = useState(0);

  // The latest fetcher is kept in a ref so dependency arrays stay under our
  // control while the effect still calls the current render's closure.
  // Synced in an effect (before the fetch effect below) rather than during
  // render, per the React refs rules.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const loadedRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    if (loadedRef.current) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    fetcherRef.current(controller.signal)
      .then((value) => {
        if (!active) return;
        loadedRef.current = true;
        setData(value);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!active || controller.signal.aborted) return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
        setRefreshing(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps are the caller's data keys; fetcher is ref-backed.
  }, [...deps, refreshKey, localRefresh]);

  const refresh = useCallback(() => {
    setLocalRefresh((value) => value + 1);
  }, []);

  return { data, error, loading, refreshing, refresh };
}
