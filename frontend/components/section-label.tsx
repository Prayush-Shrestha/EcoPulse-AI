import type { ReactNode } from "react";

interface SectionLabelProps {
  index: string;
  children: ReactNode;
}

export function SectionLabel({ index, children }: SectionLabelProps) {
  return (
    <p className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.22em] text-primary/80">
      <span className="text-muted/50">{index}</span>
      <span className="h-px w-8 bg-primary/25" aria-hidden />
      <span>{children}</span>
    </p>
  );
}
