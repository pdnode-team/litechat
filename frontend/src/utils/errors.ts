import { CUSTOM_FIELD_PREFIX } from './formLogic';

/** One rejected input, as returned by the API's uniform error payload. */
export interface ApiFieldError {
  /** Dotted path of the offending input, e.g. `title` or `custom_fields.severity`. */
  field: string;
  /** Human label of the input, when the server knows it. */
  label?: string;
  message: string;
  /** Machine readable reason, e.g. `required`, `too_short`, `not_an_option`. */
  code?: string;
}

/**
 * Shape of a Litestar error payload.
 *
 * Business errors return `{"detail": "<message>"}`; request-schema failures
 * used to return FastAPI-style `{"detail": [{"msg": "..."}]}`; every validation
 * failure now also carries `errors[]`, one entry per rejected input.
 */
export interface ApiErrorBody {
  detail?: string | Array<{ msg?: string }>;
  errors?: ApiFieldError[];
  /** Correlation id of the failed request, present on a 500. */
  request_id?: string;
  status_code?: number;
}

/** The parsed error body of a failed request, if there is one. */
export function apiErrorBody(err: unknown): ApiErrorBody | undefined {
  return (err as { response?: { data?: ApiErrorBody } })?.response?.data;
}

export function apiErrorStatus(err: unknown): number | undefined {
  return (err as { response?: { status?: number } })?.response?.status;
}

/**
 * Extract a human-readable message from an unknown thrown value (normally an
 * axios error), falling back to `fallback` when the payload is missing or has
 * an unexpected shape.
 *
 * The server's request id is appended when present so a user can quote it in a
 * bug report and the exact request can be found in the logs.
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const body = apiErrorBody(err);
  const detail = body?.detail;

  let message = fallback;
  if (typeof detail === 'string' && detail.trim()) {
    message = detail;
  } else if (Array.isArray(detail) && detail.length > 0) {
    message = detail[0]?.msg || fallback;
  }

  const requestId = body?.request_id;
  if (requestId && !message.includes(requestId)) {
    message = `${message} (reference: ${requestId})`;
  }
  return message;
}

/** Every field the server rejected, or an empty array. */
export function apiFieldErrors(err: unknown): ApiFieldError[] {
  const errors = apiErrorBody(err)?.errors;
  return Array.isArray(errors) ? errors : [];
}

/**
 * Re-key the server's field errors so a form can look them up directly.
 *
 * `custom_fields.severity` becomes `severity`; base fields such as `title` stay
 * as they are. The caller passes the custom-field keys it knows about so an
 * unrelated `custom_fields.*` entry cannot shadow a base field of the same name.
 */
export function fieldErrorMap(
  err: unknown,
  options: { customFieldKeys?: string[]; stripCustomPrefix?: boolean } = {},
): Record<string, string> {
  const keys = options.customFieldKeys;
  const map: Record<string, string> = {};

  apiFieldErrors(err).forEach((entry) => {
    if (!entry?.field) return;
    if (entry.field.startsWith(CUSTOM_FIELD_PREFIX)) {
      if (options.stripCustomPrefix === false) {
        map[entry.field] = entry.message;
        return;
      }
      const key = entry.field.slice(CUSTOM_FIELD_PREFIX.length);
      if (keys && !keys.includes(key)) return;
      map[key] = entry.message;
      return;
    }
    map[entry.field] = entry.message;
  });

  return map;
}
