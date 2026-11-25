"use client";

import type { ReactNode } from "react";

import { EmptyState } from "@/components/ui/States";
import { ChartSkeleton } from "@/components/ui/Skeleton";

interface ChartShellProps {
  loading?: boolean;
  empty: boolean;
  height: number;
  emptyMessage?: string;
  children: ReactNode;
}

/** Shared loading / empty / sized container for every chart. */
export function ChartShell({
  loading = false,
  empty,
  height,
  emptyMessage = "No data available for this selection.",
  children,
}: ChartShellProps) {
  if (loading) {
    return <ChartSkeleton height={height} />;
  }

  if (empty) {
    return (
      <div style={{ minHeight: height }} className="flex items-center justify-center">
        <EmptyState
          title="No data"
          description={emptyMessage}
          className="min-h-0 w-full border-0 py-8"
        />
      </div>
    );
  }

  return (
    <div style={{ height }} className="w-full min-w-0">
      {children}
    </div>
  );
}
