import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type BadgeTone = "ok" | "warning" | "danger" | "neutral" | "info";

const tones: Record<BadgeTone, string> = {
  ok: "border-primary/25 bg-primary/10 text-primary",
  warning: "border-warning/25 bg-warning/10 text-warning",
  danger: "border-danger/25 bg-danger/10 text-danger",
  neutral: "border-line bg-surface-raised text-muted",
  info: "border-accent/25 bg-accent/10 text-accent",
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  /** Adds a small status dot before the label. */
  dot?: boolean;
}

export function Badge({ tone = "neutral", children, className, dot = false }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]",
        tones[tone],
        className,
      )}
    >
      {dot ? <span className="size-1 rounded-full bg-current" aria-hidden /> : null}
      {children}
    </span>
  );
}
