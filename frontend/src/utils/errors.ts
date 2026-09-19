/**
 * Shape of a Litestar error payload. Our handlers return `{"detail": "<message>"}`
 * for business errors and FastAPI-style `{"detail": [{"msg": "..."}]}` for 422
 * request-validation failures.
 */
export interface ApiErrorBody {
  detail?: string | Array<{ msg?: string }>;
}

/**
 * Extract a human-readable message from an unknown thrown value (normally an
 * axios error), falling back to `fallback` when the payload is missing or has
 * an unexpected shape.
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: ApiErrorBody } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail[0]?.msg || fallback;
  }
  return fallback;
}
