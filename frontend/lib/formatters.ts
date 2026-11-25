/**
 * Display formatting for EcoPulse AI values.
 *
 * Backend timestamps are naive local civil time from the source dataset
 * (2006-2010) with no timezone. They are parsed component-wise and rendered
 * with a UTC formatter so the browser never shifts them into another day.
 */

const TIMESTAMP_RE =
  /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/;

/** Parse a naive ISO timestamp into a Date whose UTC fields hold the original values. */
export function parseNaive(iso: string): Date | null {
  const match = TIMESTAMP_RE.exec(iso);
  if (!match) return null;
  const [, y, mo, d, h = "0", mi = "0", s = "0"] = match;
  return new Date(Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s)));
}

function formatter(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", ...options });
}

const dateTimeFmt = formatter({
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateFmt = formatter({ day: "2-digit", month: "short", year: "numeric" });
const timeFmt = formatter({ hour: "2-digit", minute: "2-digit", hour12: false });
/** Hourly ticks carry the date too — bare times repeat across days. */
const hourTickFmt = formatter({
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const monthFmt = formatter({ month: "short", year: "numeric" });
const dayOnlyFmt = formatter({ weekday: "short", day: "2-digit", month: "short" });

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = parseNaive(iso);
  return date ? dateTimeFmt.format(date) : "—";
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = parseNaive(iso);
  return date ? dateFmt.format(date) : "—";
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = parseNaive(iso);
  return date ? timeFmt.format(date) : "—";
}

export function formatMonth(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = parseNaive(iso);
  return date ? monthFmt.format(date) : "—";
}

export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = parseNaive(iso);
  return date ? dayOnlyFmt.format(date) : "—";
}

/** Shift a naive timestamp by whole hours and return naive ISO (no timezone). */
export function shiftIsoHours(iso: string, hours: number): string {
  const date = parseNaive(iso);
  if (!date) return iso;
  return new Date(date.getTime() + hours * 3_600_000).toISOString().slice(0, 19);
}

/** `26 Nov 2010 · 21:02` for axis ticks and compact labels. */
export function formatTick(iso: string, granularity: "hour" | "day" | "month" = "day"): string {
  const date = parseNaive(iso);
  if (!date) return iso;
  if (granularity === "hour") return hourTickFmt.format(date);
  if (granularity === "month") return monthFmt.format(date);
  return formatter({ day: "2-digit", month: "short" }).format(date);
}

function decimalsFor(value: number): number {
  const abs = Math.abs(value);
  if (abs >= 10_000) return 0;
  if (abs >= 100) return 1;
  if (abs >= 1) return 2;
  if (abs === 0) return 0;
  if (abs >= 0.01) return 3;
  return 4;
}

function formatNumber(value: number, decimals?: number): string {
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: decimals ?? decimalsFor(value),
    maximumFractionDigits: decimals ?? decimalsFor(value),
  });
}

/** Energy in kWh with adaptive precision (minute values are ~0.018 kWh). */
export function formatKwh(value: number, decimals?: number): string {
  return formatNumber(value, decimals);
}

/** Power in kW. Backend minute energy equals kW / 60, so kW = kWh x 60. */
export function formatKw(value: number, decimals = 2): string {
  return formatNumber(value, decimals);
}

/** Convert a per-minute kWh value to average kW over that minute. */
export function perMinuteKwhToKw(kwhPerMinute: number): number {
  return kwhPerMinute * 60;
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-GB");
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`;
}

/** Anomaly scores are small signed floats; show four decimals. */
export function formatScore(value: number): string {
  return value.toFixed(4);
}

export function formatSignedPercent(value: number, decimals = 1): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}
