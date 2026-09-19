import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { NotificationSocketClient, RealtimeEvent, RealtimeStatus } from '../api/notifications';
import { useAuth } from './AuthContext';

type Handler = (event: RealtimeEvent) => void;

interface RealtimeContextValue {
  status: RealtimeStatus;
  /** Subscribe to specific event types. Returns an unsubscribe function. */
  subscribe: (types: string[], handler: Handler) => () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | undefined>(undefined);

/**
 * Keeps one notification socket for the whole session and fans events out to
 * whichever components care about them.
 *
 * Handlers are held in refs, so subscribing never re-renders and a handler
 * always sees fresh closure state.
 */
export const RealtimeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, refreshUser } = useAuth();
  const [status, setStatus] = useState<RealtimeStatus>('closed');

  const clientRef = useRef<NotificationSocketClient | null>(null);
  const subscriptionsRef = useRef<Array<{ types: Set<string>; handler: Handler }>>([]);
  // Read the id from a ref so the socket effect does not depend on the whole
  // user object (refreshUser replaces it, which would reconnect every time).
  const userIdRef = useRef<number | null>(null);

  useEffect(() => {
    userIdRef.current = user?.id ?? null;
  }, [user?.id]);

  const subscribe = useCallback((types: string[], handler: Handler) => {
    const entry = { types: new Set(types), handler };
    subscriptionsRef.current = [...subscriptionsRef.current, entry];
    return () => {
      subscriptionsRef.current = subscriptionsRef.current.filter((item) => item !== entry);
    };
  }, []);

  // Connect while signed in; tear down on sign-out.
  useEffect(() => {
    if (!user) {
      clientRef.current?.disconnect();
      clientRef.current = null;
      setStatus('closed');
      return;
    }

    const client = new NotificationSocketClient();
    clientRef.current = client;

    const offStatus = client.onStatus(setStatus);
    const offMessage = client.onMessage((event) => {
      // A role change alters what this session may do. Refreshing the profile
      // replaces `user`, which tears this effect down and reconnects with the
      // new role — the server then puts us in the right rooms.
      if (event.type === 'user_updated' && event.user_id === userIdRef.current) {
        void refreshUser();
      }
      subscriptionsRef.current.forEach(({ types, handler }) => {
        if (types.has(event.type)) handler(event);
      });
    });

    client.connect();

    return () => {
      offMessage();
      offStatus();
      client.disconnect();
    };
  }, [user, refreshUser]);

  const value = useMemo<RealtimeContextValue>(() => ({ status, subscribe }), [status, subscribe]);

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
};

export const useRealtime = (): RealtimeContextValue => {
  const context = useContext(RealtimeContext);
  if (!context) {
    throw new Error('useRealtime must be used within a RealtimeProvider');
  }
  return context;
};

/**
 * Run ``handler`` whenever one of ``types`` arrives.
 *
 * The handler is stored in a ref so callers can pass an inline closure without
 * resubscribing on every render.
 */
export const useRealtimeEvent = (types: string[], handler: Handler): void => {
  const { subscribe } = useRealtime();
  const handlerRef = useRef(handler);
  const typesKey = types.join('|');

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    const unsubscribe = subscribe(typesKey.split('|'), (event) => handlerRef.current(event));
    return unsubscribe;
  }, [subscribe, typesKey]);
};
