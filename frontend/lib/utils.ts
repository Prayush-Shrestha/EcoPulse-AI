/** Small shared helpers: class merging, date-range utilities. */

export type ClassValue = string | number | null | undefined | false;

/** Merge conditional class names (tiny `cn` without a dependency). */
export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}

export interface DateRange {
  /** Inclusive `YYYY-MM-DD` start. */
  start?: string;
  /** Inclusive `YYYY-MM-DD` end. */
  end?: string;
}

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})/;

/** Extract the `YYYY-MM-DD` part of a naive timestamp for `<input type="date">`. */
export function dateInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const match = DATE_RE.exec(iso);
  return match ? match[0] : "";
}

/** Expand a date-only range into inclusive naive timestamps for the API. */
export function toApiRange(range: DateRange | undefined): { start?: string; end?: string } {
  if (!range?.start && !range?.end) return {};
  return {
    start: range.start ? `${range.start}T00:00:00` : undefined,
    end: range.end ? `${range.end}T23:59:59` : undefined,
  };
}

/** Subtract whole days from a `YYYY-MM-DD` string (UTC maths on date parts). */
export function shiftDays(dateInput: string, days: number): string {
  const match = DATE_RE.exec(dateInput);
  if (!match) return dateInput;
  const base = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  const shifted = new Date(base + days * 86_400_000);
  return shifted.toISOString().slice(0, 10);
}

/** Last `days` days ending on `endInput`, as an inclusive date range. */
export function lastDaysRange(endInput: string, days: number): DateRange {
  return { start: shiftDays(endInput, -(days - 1)), end: endInput };
}
