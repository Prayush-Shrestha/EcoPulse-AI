"use client";

import { CalendarDays, Menu, RefreshCw, X } from "lucide-react";
import { usePathname } from "next/navigation";

import { findNavItem } from "@/components/layout/nav";
import { Badge } from "@/components/ui/Badge";
import { useApp } from "@/lib/app-context";
import { useHealth } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

interface HeaderProps {
  onOpenMobileNav: () => void;
}

function ApiStatusPill() {
  const { data, error, checking } = useHealth();

  if (checking && !data && !error) {
    return <Badge tone="neutral" dot>Connecting</Badge>;
  }
  if (error || !data) {
    return <Badge tone="danger" dot>API offline</Badge>;
  }
  if (data.status === "ok") {
    return <Badge tone="ok" dot>API online</Badge>;
  }
  return <Badge tone="warning" dot>API degraded</Badge>;
}

export function Header({ onOpenMobileNav }: HeaderProps) {
  const pathname = usePathname();
  const item = findNavItem(pathname);
  const { range, setRange, refresh } = useApp();

  const hasRange = Boolean(range.start || range.end);

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur-md">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onOpenMobileNav}
          aria-label="Open navigation"
          className="grid size-9 shrink-0 place-items-center rounded-lg border border-line text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 lg:hidden"
        >
          <Menu className="size-4" />
        </button>

        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[15px] font-medium tracking-[-0.015em] text-ink">
            {item.label}
          </h1>
          <p className="hidden truncate text-xs text-muted sm:block">{item.subtitle}</p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <div
            className="flex items-center gap-1.5 rounded-lg border border-line bg-canvas px-2 py-1.5"
            role="group"
            aria-label="Date range filter"
          >
            <CalendarDays className="size-3.5 shrink-0 text-muted/70" aria-hidden />
            <input
              type="date"
              value={range.start ?? ""}
              onChange={(event) =>
                setRange({ ...range, start: event.target.value || undefined })
              }
              aria-label="Range start date"
              className="w-[112px] bg-transparent font-mono text-[11px] text-ink outline-none"
            />
            <span className="text-muted/40" aria-hidden>
              –
            </span>
            <input
              type="date"
              value={range.end ?? ""}
              onChange={(event) =>
                setRange({ ...range, end: event.target.value || undefined })
              }
              aria-label="Range end date"
              className="w-[112px] bg-transparent font-mono text-[11px] text-ink outline-none"
            />
            {hasRange && (
              <button
                type="button"
                onClick={() => setRange({})}
                aria-label="Clear date range"
                className="grid size-5 place-items-center rounded text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
              >
                <X className="size-3" />
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={refresh}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-2",
              "font-mono text-[10px] uppercase tracking-[0.1em] text-muted",
              "transition-colors hover:border-primary/30 hover:text-ink",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
            )}
          >
            <RefreshCw className="size-3.5" aria-hidden />
            Refresh
          </button>

          <ApiStatusPill />
        </div>
      </div>
    </header>
  );
}
