import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-raised", className)}
      aria-hidden
    />
  );
}

/** Chart-shaped placeholder shown while a series loads. */
export function ChartSkeleton({ height = 260 }: { height?: number }) {
  return (
    <div
      className="flex items-end gap-2 px-1 pb-6 pt-2"
      style={{ height }}
      role="status"
      aria-label="Loading chart data"
    >
      {Array.from({ length: 12 }, (_, index) => (
        <Skeleton
          key={index}
          className="flex-1"
          // Varied heights read as a chart placeholder, not a layout bug.
        />
      ))}
    </div>
  );
}

export function KpiSkeleton() {
  return (
    <div className="panel p-5" role="status" aria-label="Loading metric">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-4 h-7 w-32" />
      <Skeleton className="mt-3 h-3 w-40" />
    </div>
  );
}
