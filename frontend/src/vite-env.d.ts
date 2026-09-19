/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** REST base URL. Relative (`/api`) by default; set absolute for a split deployment. */
  readonly VITE_API_BASE_URL?: string;
  /** Optional override for the WebSocket origin, e.g. `wss://api.example.com`. */
  readonly VITE_WS_ORIGIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
