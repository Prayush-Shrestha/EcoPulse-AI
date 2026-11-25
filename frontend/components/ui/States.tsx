"use client";

import { AlertTriangle, Inbox, RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface StateProps {
  title: string;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
}

function BaseState({ title, description, action, className, icon }: StateProps & {
  icon: ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex min-h-[180px] flex-col items-center justify-center rounded-xl border border-dashed border-line px-6 py-10 text-center",
        className,
      )}
    >
      <span className="grid size-10 place-items-center rounded-full border border-line bg-canvas text-muted">
        {icon}
      </span>
      <p className="mt-4 text-sm font-medium text-ink">{title}</p>
      <div className="mt-1.5 max-w-md text-xs leading-5 text-muted">
        {description}
      </div>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function EmptyState(props: StateProps) {
  return <BaseState {...props} icon={<Inbox className="size-4" />} />;
}

export function ErrorState({
  error,
  onRetry,
  title = "Could not load data",
}: StatePropsPartial) {
  const message =
    error instanceof Error ? error.message : "An unexpected error occurred.";

  return (
    <BaseState
      title={title}
      description={
        <>
          {message}
          <span className="mt-1 block text-muted/70">
            Check that the FastAPI backend is running, then retry.
          </span>
        </>
      }
      icon={<AlertTriangle className="size-4 text-warning" />}
      action={
        onRetry ? (
          <button type="button" onClick={onRetry} className="btn-secondary !px-4 !py-2 text-xs">
            <RotateCw className="size-3.5" />
            Retry
          </button>
        ) : undefined
      }
    />
  );
}

interface StatePropsPartial {
  error: Error | null;
  onRetry?: () => void;
  title?: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}
