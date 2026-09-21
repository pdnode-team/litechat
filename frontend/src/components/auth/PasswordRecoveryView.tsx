import React, { useEffect, useState } from 'react';
import { ArrowRight, CheckCircle2, KeyRound, Lock, MailCheck, ShieldAlert } from 'lucide-react';
import { authApi } from '../../api/client';
import { apiErrorMessage } from '../../utils/errors';

export type RecoveryTokens = { reset: string | null; verify: string | null; emailChange: string | null };

/** Reads a one-time token from the URL and then strips it from the address bar. */
const takeToken = (key: 'reset_token' | 'verify_token' | 'email_change_token'): string | null => {
  const params = new URLSearchParams(window.location.search);
  const token = params.get(key);
  if (!token) return null;
  params.delete(key);
  const query = params.toString();
  window.history.replaceState({}, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
  return token;
};

/** Capture both recovery tokens and strip them from the URL in one pass. */
export const takeRecoveryTokens = (): RecoveryTokens => ({
  reset: takeToken('reset_token'),
  verify: takeToken('verify_token'),
  emailChange: takeToken('email_change_token'),
});

export const ResetPasswordView: React.FC<{
  token: string;
  onDone: () => void;
}> = ({ token, onDone }) => {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError('The two passwords do not match.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(apiErrorMessage(err, 'This reset link is invalid or has expired.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Shell icon={<KeyRound className="w-4 h-4 text-amber-400" />} title="Choose a new password">
      {done ? (
        <Result
          tone="ok"
          message="Your password has been updated."
          actionLabel="Continue to sign in"
          onAction={onDone}
        />
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3.5">
          {error && <ErrorBox message={error} />}

          <Field label="New password">
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className={inputClass}
            />
          </Field>

          <Field label="Confirm new password">
            <input
              type="password"
              required
              minLength={8}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="••••••••"
              className={inputClass}
            />
            <p className="mt-1 text-[10px] font-mono text-zinc-500">
              At least 8 characters, containing letters and digits.
            </p>
          </Field>

          <button type="submit" disabled={loading} className={primaryButtonClass}>
            {loading ? 'Updating...' : 'Set new password'}
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>
      )}
    </Shell>
  );
};

export const VerifyEmailView: React.FC<{
  token: string;
  onDone: () => void;
  mode?: 'verify' | 'email-change';
}> = ({ token, onDone, mode = 'verify' }) => {
  const [state, setState] = useState<'working' | 'ok' | 'failed'>('working');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    const request =
      mode === 'email-change' ? authApi.verifyEmailChange(token) : authApi.verifyEmail(token);
    request
      .then(() => {
        if (!cancelled) setState('ok');
      })
      .catch((err) => {
        if (cancelled) return;
        setMessage(apiErrorMessage(err, 'This verification link is invalid or has expired.'));
        setState('failed');
      });
    return () => {
      cancelled = true;
    };
  }, [token, mode]);

  return (
    <Shell icon={<MailCheck className="w-4 h-4 text-emerald-400" />} title="Email confirmation">
      {state === 'working' && (
        <p className="py-4 text-center text-xs font-mono text-zinc-500">Confirming your address...</p>
      )}
      {state === 'ok' && (
        <Result
          tone="ok"
          message={
            mode === 'email-change'
              ? 'Your email address has been updated.'
              : 'Your email address is confirmed.'
          }
          actionLabel="Continue to sign in"
          onAction={onDone}
        />
      )}
      {state === 'failed' && (
        <Result tone="error" message={message} actionLabel="Back to sign in" onAction={onDone} />
      )}
    </Shell>
  );
};

/** Chooses the right recovery screen for tokens captured at app bootstrap. */
export const PasswordRecoveryGate: React.FC<{ tokens: RecoveryTokens }> = ({ tokens }) => {
  if (tokens.reset) return <ResetPasswordView token={tokens.reset} onDone={() => window.location.reload()} />;
  if (tokens.verify) return <VerifyEmailView token={tokens.verify} onDone={() => window.location.reload()} />;
  if (tokens.emailChange) {
    return <VerifyEmailView token={tokens.emailChange} onDone={() => window.location.reload()} mode="email-change" />;
  }
  return null;
};

/** True when the URL carries a recovery token, i.e. the gate should take over. */
export const hasRecoveryToken = (): boolean => {
  const params = new URLSearchParams(window.location.search);
  return params.has('reset_token') || params.has('verify_token') || params.has('email_change_token');
};

const inputClass =
  'w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition';
const primaryButtonClass =
  'w-full py-2.5 px-4 bg-zinc-100 hover:bg-white text-zinc-900 text-xs font-semibold rounded-lg transition shadow-sm flex items-center justify-center gap-1.5 disabled:opacity-50 mt-2';

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <label className="block text-xs font-mono text-zinc-400 mb-1 uppercase tracking-wider">
      {label}
    </label>
    {children}
  </div>
);

const ErrorBox: React.FC<{ message: string }> = ({ message }) => (
  <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-900 text-rose-300 text-xs font-medium">
    {message}
  </div>
);

const Result: React.FC<{
  tone: 'ok' | 'error';
  message: string;
  actionLabel: string;
  onAction: () => void;
}> = ({ tone, message, actionLabel, onAction }) => (
  <div className="text-center py-4">
    <div
      className={`w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-3 border ${
        tone === 'ok'
          ? 'bg-emerald-950/80 border-emerald-800 text-emerald-400'
          : 'bg-rose-950/80 border-rose-900 text-rose-400'
      }`}
    >
      {tone === 'ok' ? <CheckCircle2 className="w-5 h-5" /> : <ShieldAlert className="w-5 h-5" />}
    </div>
    <p className="text-xs text-zinc-300 mb-4">{message}</p>
    <button type="button" onClick={onAction} className={primaryButtonClass}>
      {actionLabel}
      <ArrowRight className="w-3.5 h-3.5" />
    </button>
  </div>
);

const Shell: React.FC<{ icon: React.ReactNode; title: string; children: React.ReactNode }> = ({
  icon,
  title,
  children,
}) => (
  <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col justify-center items-center p-4 selection:bg-zinc-700 selection:text-white">
    <div className="w-full max-w-sm">
      <div className="mb-8 text-center">
        <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-400 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          LITECHAT // DISPATCH
        </div>
        <h1 className="text-xl font-bold tracking-tight text-zinc-100">{title}</h1>
      </div>

      <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-6 shadow-2xl backdrop-blur-md">
        <div className="mb-4 flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-zinc-400">
          <Lock className="w-3.5 h-3.5 text-zinc-500" />
          <span>Account security</span>
          <span className="ml-auto">{icon}</span>
        </div>
        {children}
      </div>
    </div>
  </div>
);
