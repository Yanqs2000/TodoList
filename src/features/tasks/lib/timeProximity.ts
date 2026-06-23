import type { TimeField } from '@/shared/types';

/**
 * Time-proximity classification for the Today Focus timeline.
 * `now` is passed in by callers (and tests) so these stay pure & deterministic —
 * the app convention is that TimeField.start ISO strings ("YYYY-MM-DDTHH:mm")
 * are interpreted as local time (see useReminders).
 */

export type Proximity = 'overdue' | 'soon' | 'today' | 'future' | 'none';

const SOON_WINDOW_MS = 60 * 60 * 1000; // 1 hour

/** Parse a local ISO datetime string ("YYYY-MM-DDTHH:mm") → epoch ms, or null. */
export function parseTimeStart(iso: string): number | null {
  const ts = new Date(iso).getTime();
  return Number.isFinite(ts) ? ts : null;
}

/** Whether `iso` falls on the same calendar day (local) as `now`. */
export function isToday(iso: string, now: number): boolean {
  const ts = parseTimeStart(iso);
  if (ts === null) return false;
  const a = new Date(ts);
  const b = new Date(now);
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

/**
 * Classify a task's time relative to `now`:
 * - `none`    — no time set
 * - `overdue` — start is in the past
 * - `soon`    — starts within the next hour
 * - `today`   — starts later today
 * - `future`  — starts on a future calendar day
 */
export function proximityOf(time: TimeField | undefined, now: number): Proximity {
  if (!time?.start) return 'none';
  const due = parseTimeStart(time.start);
  if (due === null) return 'none';
  if (due <= now) return 'overdue';
  if (due - now <= SOON_WINDOW_MS) return 'soon';
  if (isToday(time.start, now)) return 'today';
  return 'future';
}

/**
 * Map a local time-of-day onto the 06:00–24:00 timeline as a percentage (0–100).
 * Times before 06:00 clamp to 0. Returns null for unparseable input.
 */
export function toTimelineX(iso: string): number | null {
  const ts = parseTimeStart(iso);
  if (ts === null) return null;
  const d = new Date(ts);
  const hours = d.getHours() + d.getMinutes() / 60;
  const clamped = Math.max(6, hours);
  return ((clamped - 6) / 18) * 100;
}
