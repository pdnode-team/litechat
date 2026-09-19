export type WebSocketEventHandler = (data: any) => void;

export class TicketWebSocketClient {
  private ticketId: number;
  private ws: WebSocket | null = null;
  private token: string | null;
  private handlers: Set<WebSocketEventHandler> = new Set();
  private shouldReconnect: boolean = true;
  private reconnectTimeout: any = null;

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

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/tickets/${this.ticketId}${
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
          const data = JSON.parse(event.data);
          this.handlers.forEach((h) => h(data));
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
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
