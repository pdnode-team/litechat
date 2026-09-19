import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { authApi } from '../../api/client';
import { ArrowRight, Lock, Mail, ShieldAlert } from 'lucide-react';

type Mode = 'login' | 'register' | 'setup';

/** Litestar returns a plain string for our errors, but an array for 422 validation. */
const errorText = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) return detail[0]?.msg ?? fallback;
  return fallback;
};

export const AuthView: React.FC = () => {
  const { login, register, setupAdmin } = useAuth();
  const [mode, setMode] = useState<Mode>('login');
  const [checkingDeployment, setCheckingDeployment] = useState(true);

  // Login fields
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');

  // Register / bootstrap fields (shared: both create an account from scratch)
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A fresh install has no users at all, so registration alone can never yield
  // an administrator. Probe once and offer the one-shot bootstrap form instead.
  useEffect(() => {
    let cancelled = false;
    authApi
      .getBootstrapStatus()
      .then(({ needs_setup }) => {
        if (cancelled || !needs_setup) return;
        setMode('setup');
      })
      .catch(() => {
        // Advisory only — fall back to the normal sign-in screen.
      })
      .finally(() => {
        if (!cancelled) setCheckingDeployment(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier || !password) return;
    setLoading(true);
    setError(null);
    try {
      await login(identifier, password);
    } catch (err: any) {
      setError(errorText(err, 'Invalid username or password.'));
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !username || !fullName || !regPassword) return;
    setLoading(true);
    setError(null);
    try {
      await register(email, username, fullName, regPassword);
    } catch (err: any) {
      setError(errorText(err, 'Registration failed. Email or username may already exist.'));
    } finally {
      setLoading(false);
    }
  };

  const handleSetupAdmin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !username || !fullName || !regPassword) return;
    setLoading(true);
    setError(null);
    try {
      await setupAdmin(email, username, fullName, regPassword);
    } catch (err: any) {
      setError(errorText(err, 'Could not create the administrator account.'));
    } finally {
      setLoading(false);
    }
  };

  const heading =
    mode === 'setup' ? 'Initialize LiteChat' : mode === 'register' ? 'Create Account' : 'Sign in to LiteChat';

  const subheading =
    mode === 'setup'
      ? 'This deployment has no accounts yet. The account created here becomes the administrator.'
      : mode === 'register'
      ? 'New accounts are created as Customers.'
      : 'Enter your credentials to access your support workspace.';

  const accountForm = mode === 'setup' ? handleSetupAdmin : handleRegister;
  const submitLabel = mode === 'setup' ? 'Create Administrator' : 'Create Account';

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col justify-center items-center p-4 selection:bg-zinc-700 selection:text-white">
      <div className="w-full max-w-sm">
        {/* Brand Header */}
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-400 mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            LITECHAT // DISPATCH
          </div>
          <h1 className="text-xl font-bold tracking-tight text-zinc-100">{heading}</h1>
          <p className="text-xs text-zinc-400 mt-1">{subheading}</p>
        </div>

        {/* Form Card */}
        <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-6 shadow-2xl backdrop-blur-md">
          {mode === 'setup' && (
            <div className="mb-4 p-3 rounded-lg bg-amber-950/50 border border-amber-900 text-amber-200 text-xs flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 flex-shrink-0 mt-px text-amber-400" />
              <span>
                First-run setup. This form is locked automatically once any account exists.
              </span>
            </div>
          )}

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-rose-950/60 border border-rose-900 text-rose-300 text-xs font-medium">
              {error}
            </div>
          )}

          {checkingDeployment ? (
            <div className="py-6 text-center text-xs font-mono text-zinc-500">
              Checking deployment state...
            </div>
          ) : mode === 'login' ? (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-xs font-mono text-zinc-400 mb-1.5 uppercase tracking-wider">
                  Username or Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    required
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="name@domain.com"
                    className="w-full text-xs pl-9 pr-3 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-mono text-zinc-400 mb-1.5 uppercase tracking-wider">
                  Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full text-xs pl-9 pr-3 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 bg-zinc-100 hover:bg-white text-zinc-900 text-xs font-semibold rounded-lg transition shadow-sm flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                {loading ? 'Authenticating...' : 'Sign In'}
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </form>
          ) : (
            <form onSubmit={accountForm} className="space-y-3.5">
              <div>
                <label className="block text-xs font-mono text-zinc-400 mb-1 uppercase tracking-wider">
                  Full Name
                </label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Alex Morgan"
                  className="w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-zinc-400 mb-1 uppercase tracking-wider">
                  Username
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="alexm"
                  className="w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-zinc-400 mb-1 uppercase tracking-wider">
                  Email
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="alex@example.com"
                  className="w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-zinc-400 mb-1 uppercase tracking-wider">
                  Password
                </label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition"
                />
                <p className="mt-1 text-[10px] font-mono text-zinc-500">
                  At least 8 characters, containing letters and digits.
                </p>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 bg-zinc-100 hover:bg-white text-zinc-900 text-xs font-semibold rounded-lg transition shadow-sm flex items-center justify-center gap-1.5 disabled:opacity-50 mt-2"
              >
                {loading ? 'Working...' : submitLabel}
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </form>
          )}

          {/* Mode switches */}
          {!checkingDeployment && (
            <div className="mt-5 pt-4 border-t border-zinc-800/80 text-center space-y-2">
              {mode === 'login' ? (
                <button
                  type="button"
                  onClick={() => {
                    setMode('register');
                    setError(null);
                  }}
                  className="text-xs text-zinc-400 hover:text-zinc-200 transition"
                >
                  Don't have an account? Create one
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setMode('login');
                    setError(null);
                  }}
                  className="text-xs text-zinc-400 hover:text-zinc-200 transition"
                >
                  Already have an account? Sign In
                </button>
              )}

              {mode === 'setup' && (
                <p className="text-[10px] font-mono text-zinc-600">
                  Prefer the CLI? See backend/README.md
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
