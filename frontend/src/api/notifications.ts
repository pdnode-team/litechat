/**
 * Account-wide notification socket.
 *
 * ``/ws/tickets/{id}`` carries one conversation; this channel carries every
 * other state change the user is allowed to see (new tickets in the queue,
 * status/role/catalogue changes, ratings, rate-limit notices), so the UI never
 * has to poll.
 */

import { authApi } from './client';
import { wsOrigin } from './config';

export interface RealtimeEvent {
  type: string;
  [key: string]: unknown;
}
export type RealtimeStatus = 'connecting' | 'open' | 'closed';

type MessageHandler = (event: RealtimeEvent) => void;
type StatusHandler = (status: RealtimeStatus) => void;

const MAX_RECONNECT_ATTEMPTS = 15;
const AUTH_CLOSE_CODES = new Set([4401, 4403, 4404, 1008]);

export class NotificationSocketClient {
  private ws: WebSocket | null = null;
  private handlers = new Set<MessageHandler>();
  private statusHandlers = new Set<StatusHandler>();
  private shouldReconnect = true;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private attempts = 0;
  private status: RealtimeStatus = 'closed';
  private connectGeneration = 0;

  constructor() {}

  public onMessage(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  public onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler);
    handler(this.status);
    return () => {
      this.statusHandlers.delete(handler);
    };
  }

  private setStatus(next: RealtimeStatus): void {
    if (this.status === next) return;
    this.status = next;
    this.statusHandlers.forEach((handler) => handler(next));
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.shouldReconnect = true;
    void this.openSocket();
  }

  private async openSocket(): Promise<void> {
    const generation = ++this.connectGeneration;
    let token: string | null = null;
    try {
      token = (await authApi.createWsTicket()).token;
    } catch {
      token = localStorage.getItem('litechat_token');
    }
    if (generation !== this.connectGeneration || !this.shouldReconnect) return;

    const url = `${wsOrigin()}/ws/notifications${
      token ? `?token=${encodeURIComponent(token)}` : ''
    }`;

    this.setStatus('connecting');
    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.attempts = 0;
        this.setStatus('open');
      };

      this.ws.onmessage = (event) => {
        let data: RealtimeEvent;
        try {
          data = JSON.parse(event.data) as RealtimeEvent;
        } catch {
          return;
        }
        this.handlers.forEach((handler) => handler(data));
      };

      this.ws.onclose = (event) => {
        this.setStatus('closed');
        if (AUTH_CLOSE_CODES.has(event.code)) {
          this.shouldReconnect = false;
          return;
        }
        if (this.shouldReconnect && this.attempts < MAX_RECONNECT_ATTEMPTS) {
          const delay = Math.min(1000 * Math.pow(1.5, this.attempts), 30000);
          this.attempts += 1;
          this.reconnectTimeout = setTimeout(() => {
            if (this.shouldReconnect) this.connect();
          }, delay);
        }
      };

      this.ws.onerror = () => {
        // onclose follows and owns the reconnect decision.
      };
    } catch {
      this.setStatus('closed');
    }
  }

  /** Drop the current connection and open a fresh one (after a role change). */
  public reconnect(): void {
    this.closeSocket();
    this.attempts = 0;
    this.shouldReconnect = true;
    this.connect();
  }

  private closeSocket(): void {
    this.connectGeneration += 1;
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  public disconnect(): void {
    this.shouldReconnect = false;
    this.closeSocket();
    this.setStatus('closed');
  }
}
