/**
 * Where the API and WebSockets live.
 *
 * Defaults keep the browser talking to its own origin, which is what the dev
 * proxy and a single-domain production reverse proxy both provide. Setting
 * `VITE_API_BASE_URL` to an absolute URL points the SPA at a separate backend
 * host instead (then `ALLOWED_ORIGINS` must include this site's origin).
 */

const rawBase = (import.meta.env.VITE_API_BASE_URL ?? '').trim();

/** Base URL for REST calls. Relative by default so a proxy can route it. */
export const API_BASE_URL = (rawBase || '/api').replace(/\/+$/, '');

const rawWsOrigin = (import.meta.env.VITE_WS_ORIGIN ?? '').trim();

/**
 * Origin (scheme + host) to open WebSockets against.
 *
 * WebSocket routes live at `/ws/...`, not under the API prefix, so only the
 * origin is taken from `VITE_WS_ORIGIN` / `VITE_API_BASE_URL`.
 */
export const wsOrigin = (): string => {
  if (rawWsOrigin) return rawWsOrigin.replace(/\/+$/, '').replace(/^http/i, 'ws');

  if (/^https?:\/\//i.test(API_BASE_URL)) {
    const url = new URL(API_BASE_URL);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.origin;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}`;
};
