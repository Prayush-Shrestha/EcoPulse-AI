"use client";

import { useEffect, useState } from "react";

import { PulseIcon, RefreshIcon } from "@/components/icons";
import { fetchHealth, type HealthResponse } from "@/lib/health";
import { siteConfig } from "@/lib/site";

const REFRESH_INTERVAL_MS = 30_000;
const REQUEST_TIMEOUT_MS = 5_000;

type HealthState =
  | { phase: "checking" }
  | { phase: "online"; data: HealthResponse; checkedAt: Date }
  | { phase: "offline"; checkedAt: Date };

type Tone = "ok" | "warning" | "danger" | "neutral";

interface Summary {
  badge: string;
  headline: string;
  detail: string;
  tone: Tone;
}

const toneStyles: Record<Tone, { badge: string; dot: string; orb: string }> = {
  ok: {
    badge: "border-primary/20 bg-primary/10 text-primary",
    dot: "bg-primary",
    orb: "border-primary/20 bg-primary/5 text-primary",
  },
  warning: {
    badge: "border-warning/20 bg-warning/10 text-warning",
    dot: "bg-warning",
    orb: "border-warning/20 bg-warning/5 text-warning",
  },
  danger: {
    badge: "border-danger/20 bg-danger/10 text-danger",
    dot: "bg-danger",
    orb: "border-danger/20 bg-danger/5 text-danger",
  },
  neutral: {
    badge: "border-line bg-surface-raised text-muted",
    dot: "bg-muted/50",
    orb: "border-line bg-canvas text-muted",
  },
};

const timeFormatter = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

function getSummary(state: HealthState): Summary {
  if (state.phase === "checking") {
    return {
      badge: "Checking",
      headline: "Running foundation checks",
      detail: "Querying the local FastAPI health contract.",
      tone: "neutral",
    };
  }

  if (state.phase === "offline") {
    return {
      badge: "Offline",
      headline: "API is not reachable",
      detail:
        "Start FastAPI on port 8000. This panel retries every 30 seconds.",
      tone: "danger",
    };
  }

  if (state.data.status === "ok") {
    return {
      badge: "Operational",
      headline: "Foundation healthy",
      detail: "The API and PostgreSQL are responding on this machine.",
      tone: "ok",
    };
  }

  return {
    badge: "Degraded",
    headline: "Database check failed",
    detail:
      "The API is reachable, but PostgreSQL is not responding. Check the db service.",
    tone: "warning",
  };
}

export function StatusPanel() {
  const [state, setState] = useState<HealthState>({ phase: "checking" });
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      REQUEST_TIMEOUT_MS,
    );

    fetchHealth(controller.signal)
      .then((data) => {
        if (active) {
          setState({ phase: "online", data, checkedAt: new Date() });
        }
      })
      .catch(() => {
        if (active) {
          setState({ phase: "offline", checkedAt: new Date() });
        }
      })
      .finally(() => window.clearTimeout(timeout));

    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [refreshToken]);

  useEffect(() => {
    const interval = window.setInterval(
      () => setRefreshToken((value) => value + 1),
      REFRESH_INTERVAL_MS,
    );

    return () => window.clearInterval(interval);
  }, []);

  const summary = getSummary(state);
  const styles = toneStyles[summary.tone];

  const apiValue =
    state.phase === "checking"
      ? "Checking"
      : state.phase === "offline"
        ? "Unreachable"
        : state.data.checks.api?.status === "ok"
          ? "Operational"
          : "Unavailable";

  const apiTone: Tone =
    state.phase === "checking"
      ? "neutral"
      : state.phase === "offline"
        ? "danger"
        : state.data.checks.api?.status === "ok"
          ? "ok"
          : "warning";

  const databaseValue =
    state.phase === "checking"
      ? "Checking"
      : state.phase === "offline"
        ? "Unknown"
        : state.data.checks.database?.status === "ok"
          ? "Connected"
          : "Unavailable";

  const databaseTone: Tone =
    state.phase === "checking" || state.phase === "offline"
      ? "neutral"
      : state.data.checks.database?.status === "ok"
        ? "ok"
        : "danger";

  const rows: Array<{ label: string; value: string; tone: Tone }> = [
    { label: "Web interface", value: "Online", tone: "ok" },
    { label: "FastAPI service", value: apiValue, tone: apiTone },
    { label: "PostgreSQL", value: databaseValue, tone: databaseTone },
  ];

  const meta =
    state.phase === "online"
      ? `${state.data.environment} · v${state.data.version}`
      : `local · v${siteConfig.version}`;

  const checkedLabel =
    state.phase === "checking"
      ? "Awaiting first check"
      : `Checked ${timeFormatter.format(state.checkedAt)}`;

  return (
    <figure className="relative">
      <div className="relative overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_30px_80px_-40px_rgba(0,0,0,0.9)]">
        <div
          className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute -right-20 -top-24 size-56 rounded-full bg-primary/5 blur-3xl"
          aria-hidden
        />

        <div className="relative p-6 sm:p-7">
          <div className="flex items-center justify-between gap-4">
            <p className="eyebrow text-muted">Runtime checks</p>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.12em] ${styles.badge}`}
              aria-live="polite"
            >
              <span
                className={`size-1 rounded-full ${styles.dot}`}
                aria-hidden
              />
              {summary.badge}
            </span>
          </div>

          <div className="mt-8 flex items-center gap-4">
            <div
              className={`relative grid size-14 shrink-0 place-items-center rounded-full border ${styles.orb}`}
            >
              {state.phase === "online" && state.data.status === "ok" ? (
                <span
                  className="absolute inset-0 rounded-full border border-primary/30 animate-pulse-ring"
                  aria-hidden
                />
              ) : null}
              <PulseIcon className="size-6" />
            </div>
            <div className="min-w-0">
              <p
                className="text-lg font-medium tracking-[-0.025em] text-ink"
                aria-live="polite"
              >
                {summary.headline}
              </p>
              <p className="mt-1 text-xs leading-5 text-muted">
                {summary.detail}
              </p>
            </div>
          </div>

          <dl className="mt-8 divide-y divide-line/60 border-y border-line/60">
            {rows.map((row) => (
              <div
                key={row.label}
                className="flex items-center justify-between gap-4 py-3"
              >
                <dt className="text-xs text-muted">{row.label}</dt>
                <dd className="flex items-center gap-2 text-xs font-medium text-ink">
                  <span
                    className={`size-1.5 rounded-full ${toneStyles[row.tone].dot}`}
                    aria-hidden
                  />
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>

          <div className="mt-4 flex items-center justify-between gap-3">
            <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted/60">
              {meta}
            </span>
            <button
              type="button"
              onClick={() => setRefreshToken((value) => value + 1)}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted transition-colors hover:border-primary/30 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              <RefreshIcon className="size-3" />
              Recheck
            </button>
          </div>

          <div className="mt-4 border-t border-line/50 pt-3">
            <p className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted/50">
              {checkedLabel}
            </p>
          </div>
        </div>
      </div>

      <figcaption className="mt-4 px-1 text-[11px] leading-5 text-muted/60">
        The only live values in Phase 1 are infrastructure checks. No
        consumption data or model output is simulated.
      </figcaption>
    </figure>
  );
}
