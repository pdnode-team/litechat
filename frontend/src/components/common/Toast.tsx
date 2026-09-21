import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, X } from 'lucide-react';

type ToastTone = 'success' | 'error';

interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastContextValue {
  showSuccess: (message: string) => void;
  showError: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

/**
 * Minimal toast surface.
 *
 * Mutations used to fail with only a `console.error`, so a failed delete or
 * status change looked exactly like a successful one. Components now surface
 * those failures here.
 */
export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (tone: ToastTone, message: string) => {
      const id = Date.now() + Math.random();
      setToasts((prev) => [...prev, { id, tone, message }]);
      const timer = window.setTimeout(() => dismiss(id), tone === 'error' ? 6000 : 3500);
      timers.current.push(timer);
    },
    [dismiss]
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      showSuccess: (message: string) => push('success', message),
      showError: (message: string) => push('error', message),
    }),
    [push]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm"
        role="region"
        aria-label="Notifications"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="alert"
            className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs shadow-2xl backdrop-blur-md ${
              toast.tone === 'error'
                ? 'bg-rose-950/90 border-rose-900 text-rose-200'
                : 'bg-emerald-950/90 border-emerald-900 text-emerald-200'
            }`}
          >
            {toast.tone === 'error' ? (
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-px text-rose-400" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 mt-px text-emerald-400" />
            )}
            <span className="flex-1">{toast.message}</span>
            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss notification"
              className="p-0.5 rounded opacity-70 hover:opacity-100 transition"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextValue => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};
