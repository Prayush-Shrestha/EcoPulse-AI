import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Removes the body padding for charts that manage their own spacing. */
  flush?: boolean;
}

/** Surface card used across the dashboard. */
export function Card({
  title,
  subtitle,
  action,
  footer,
  children,
  className,
  flush = false,
}: CardProps) {
  return (
    <section className={cn("panel flex min-w-0 flex-col", className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-line/60 px-5 py-4">
          <div className="min-w-0">
            {title ? (
              <h2 className="truncate text-sm font-medium tracking-[-0.01em] text-ink">
                {title}
              </h2>
            ) : null}
            {subtitle ? (
              <p className="mt-1 text-xs leading-5 text-muted">{subtitle}</p>
            ) : null}
          </div>
          {action ? <div className="shrink-0">{action}</div> : null}
        </header>
      )}
      <div className={cn("flex-1", flush ? "p-0" : "px-5 py-4")}>{children}</div>
      {footer ? (
        <footer className="border-t border-line/60 px-5 py-3">{footer}</footer>
      ) : null}
    </section>
  );
}
