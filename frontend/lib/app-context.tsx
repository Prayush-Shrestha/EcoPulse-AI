"use client";

/**
 * App-wide UI state shared by the header and data hooks:
 * a date range selected in the header, and a refresh token that
 * invalidates cached GET responses and refetches mounted hooks.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { clearApiCache } from "@/lib/api";
import type { DateRange } from "@/lib/utils";

interface AppContextValue {
  /** Header-selected inclusive date range; empty means "backend default window". */
  range: DateRange;
  setRange: (range: DateRange) => void;
  /** Bumped by the header refresh button; consumed by every data hook. */
  refreshKey: number;
  refresh: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [range, setRange] = useState<DateRange>({});
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => {
    clearApiCache();
    setRefreshKey((value) => value + 1);
  }, []);

  const value = useMemo(
    () => ({ range, setRange, refreshKey, refresh }),
    [range, refreshKey, refresh],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useApp must be used inside <AppProvider>");
  }
  return context;
}
