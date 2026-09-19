import type { Message, Ticket, UserRole } from '../types';
import { wsOrigin } from './config';

/**
 * Server -> client WebSocket payloads, mirroring what the backend hub broadcasts
 * (see backend/app/services/websocket_hub.py, controllers/messages.py,
 * controllers/tickets.py and controllers/websocket.py).
 */
export interface WsNewMessage {
  type: 'new_message';
  message: Message;
}

export interface WsTicketUpdated {
  type: 'ticket_updated';
  ticket: Ticket;
}

export interface WsTyping {
  type: 'typing';
  user_id: number;
  user_name: string;
  is_typing: boolean;
}

export interface WsPresence {
  type: 'presence';
  event: 'joined' | 'left';
  user_id: number;
  user_name: string;
  role: UserRole;
}

export type WebSocketMessage = WsNewMessage | WsTicketUpdated | WsTyping | WsPresence;

/**
 * Runtime guard for raw JSON frames. Frames that do not match a known shape are
 * dropped by the client, so consumers only ever receive `WebSocketMessage`.
 */
export function isWsMessage(value: unknown): value is WebSocketMessage {
  if (typeof value !== 'object' || value === null) return false;
  const type = (value as { type?: unknown }).type;
  return (
    type === 'new_message' ||
    type === 'ticket_updated' ||
    type === 'typing' ||
    type === 'presence'
  );
}

export type WebSocketEventHandler = (data: WebSocketMessage) => void;

export class TicketWebSocketClient {
  private ticketId: number;
  private ws: WebSocket | null = null;
  private token: string | null;
  private handlers: Set<WebSocketEventHandler> = new Set();
  private shouldReconnect: boolean = true;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;

  constructor(ticketId: number, token?: string | null) {
    this.ticketId = ticketId;
    this.token = token || localStorage.getItem('litechat_token');
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const url = `${wsOrigin()}/ws/tickets/${this.ticketId}${
      this.token ? `?token=${encodeURIComponent(this.token)}` : ''
    }`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log(`[WS] Connected to ticket room ${this.ticketId}`);
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const parsed: unknown = JSON.parse(event.data);
          if (!isWsMessage(parsed)) return;
          this.handlers.forEach((h) => h(parsed));
        } catch (err) {
          console.error('[WS] Failed to parse message', err);
        }
      };

      this.ws.onclose = (event) => {
        // Stop reconnecting on auth/policy failures
        if (event.code === 4401 || event.code === 1008) {
          console.warn(`[WS] Connection closed due to authorization failure (${event.code}). Stopping reconnect.`);
          this.shouldReconnect = false;
          return;
        }

        if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 30000);
          this.reconnectAttempts++;
          this.reconnectTimeout = setTimeout(() => {
            if (this.shouldReconnect) {
              this.connect();
            }
          }, delay);
        }
      };

      this.ws.onerror = (err) => {
        console.warn('[WS] Error on socket connection', err);
      };
    } catch (err) {
      console.error('[WS] Connection exception', err);
    }
  }

  public sendTyping(isTyping: boolean): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'typing', is_typing: isTyping }));
    }
  }

  public onMessage(handler: WebSocketEventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  public disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimeout !== null) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
