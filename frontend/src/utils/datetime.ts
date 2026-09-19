import { format } from 'date-fns';

/**
 * The backend stores timestamps as UTC but serializes them without an explicit
 * timezone designator (e.g. "2026-09-19T07:43:26.020384").
 *
 * `new Date("2026-09-19T07:43:26")` is interpreted by JavaScript as *local* time,
 * which shifts every displayed value by the client's UTC offset. Appending "Z"
 * when no offset is present makes the parse unambiguous.
 */
export const parseUtcDate = (value: string | Date): Date => {
  if (value instanceof Date) return value;
  const hasTimezone = /([Zz]|[+-]\d{2}:?\d{2})$/.test(value);
  return new Date(hasTimezone ? value : `${value}Z`);
};

/** Format a backend timestamp as UTC-anchored local time. */
export const formatUtc = (
  value: string | Date | null | undefined,
  pattern: string
): string => {
  if (!value) return '';
  return format(parseUtcDate(value), pattern);
};
