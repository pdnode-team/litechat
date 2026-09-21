import type { Message, Ticket, UserRole } from '../types';
import { authApi } from './client';
import { wsOrigin } from './config';

export interface WsNewMessage {
  type: 'new_message';
  message: Message;
}

export interface WsTicketUpdated {
  type: 'ticket_updated';
  ticket: Ticket;
  message?: Message;
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

const AUTH_CLOSE_CODES = new Set([4401, 4403, 4404, 1008]);

async function wsToken(): Promise<string | null> {
  try {
    return (await authApi.createWsTicket()).token;
  } catch {
    return localStorage.getItem('litechat_token');
  }
}

export class TicketWebSocketClient {
  private ticketId: number;
  private ws: WebSocket | null = null;
  private handlers: Set<WebSocketEventHandler> = new Set();
  private shouldReconnect: boolean = true;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private connectGeneration = 0;

  constructor(ticketId: number) {
    this.ticketId = ticketId;
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    void this.openSocket();
  }

  private async openSocket(): Promise<void> {
    const generation = ++this.connectGeneration;
    const token = await wsToken();
    if (generation !== this.connectGeneration || !this.shouldReconnect) return;

    const url = `${wsOrigin()}/ws/tickets/${this.ticketId}${
      token ? `?token=${encodeURIComponent(token)}` : ''
    }`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
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
        if (AUTH_CLOSE_CODES.has(event.code)) {
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
    this.connectGeneration += 1;
    if (this.reconnectTimeout !== null) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }
}
