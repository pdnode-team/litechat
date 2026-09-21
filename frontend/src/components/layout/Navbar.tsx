import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useRealtime, useRealtimeEvent } from '../../context/RealtimeContext';
import { authApi } from '../../api/client';
import { UserAvatar } from '../common/UserAvatar';
import { useToast } from '../common/Toast';
import { apiErrorMessage } from '../../utils/errors';
import { LogOut, MailWarning, X } from 'lucide-react';

interface NavbarProps {
  systemLabel?: string;
  badge?: string;
  children?: React.ReactNode;
  rightActions?: React.ReactNode;
}

export const Navbar: React.FC<NavbarProps> = ({
  systemLabel = 'LITECHAT',
  badge,
  children,
  rightActions,
}) => {
  const { user, logout } = useAuth();
  const { showError } = useToast();
  const { status: realtimeStatus } = useRealtime();
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [resendState, setResendState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [resendMessage, setResendMessage] = useState('');

  // The server tells us when we get throttled, so the user learns why their
  // request was rejected instead of just seeing a failure.
  useRealtimeEvent(['rate_limited'], (event) => {
    const retryAfter = typeof event.retry_after === 'number' ? event.retry_after : null;
    showError(
      retryAfter
        ? `Too many requests. Try again in ${retryAfter}s.`
        : 'Too many requests. Please slow down.'
    );
  });

  // Verification is advisory: an unconfirmed address only prompts, it never
  // blocks access, so this is a dismissible banner rather than a wall.
  const showVerifyBanner = Boolean(user && !user.email_verified && !bannerDismissed);

  const handleResend = async () => {
    setResendState('sending');
    setResendMessage('');
    try {
      const res = await authApi.resendVerification();
      setResendState('sent');
      setResendMessage(res.detail);
    } catch (err) {
      setResendState('error');
      setResendMessage(apiErrorMessage(err, 'Could not send the verification email.'));
    }
  };

  return (
    <>
      <header className="h-[3.25rem] border-b border-zinc-800/90 bg-zinc-950/80 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between sticky top-0 z-30 select-none">
        {/* Brand & System Status */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 font-mono text-xs font-semibold tracking-wider text-zinc-100">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]" />
            <span>{systemLabel}</span>
          </div>

          {badge && (
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-400">
              {badge}
            </span>
          )}
          {user && realtimeStatus !== 'open' && (
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-amber-950/70 border border-amber-800/80 text-amber-300">
              {realtimeStatus === 'connecting' ? 'Connecting live updates' : 'Live updates paused'}
            </span>
          )}

          {/* Children navigation items (e.g. Staff tabs) */}
          {children && <div className="ml-2 flex items-center gap-1">{children}</div>}
        </div>

        {/* Right User & Actions */}
        <div className="flex items-center gap-3">
          {rightActions}

          {user && (
            <div className="flex items-center gap-2.5 pl-3 border-l border-zinc-800/80">
              <UserAvatar name={user.full_name} size="sm" />
              <div className="hidden sm:flex flex-col text-left">
                <span className="text-xs font-medium text-zinc-200 leading-tight">
                  {user.full_name}
                </span>
                <span className="text-[10px] font-mono text-zinc-500 uppercase leading-none">
                  {user.role}
                </span>
              </div>

              <button
                type="button"
                onClick={logout}
                title="Sign Out"
                aria-label="Sign out"
                className="p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 rounded-md transition ml-1"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </header>

      {showVerifyBanner && (
        <div
          role="status"
          className="sticky top-[3.25rem] z-20 flex items-center gap-2 border-b border-amber-900/70 bg-amber-950/60 px-4 sm:px-6 py-2 text-[11px] text-amber-200"
        >
          <MailWarning className="w-3.5 h-3.5 flex-shrink-0 text-amber-400" />
          <span className="flex-1">
            {resendState === 'sent'
              ? resendMessage
              : resendState === 'error'
              ? resendMessage
              : `Your email address (${user?.email}) is not confirmed yet.`}
          </span>

          {resendState !== 'sent' && (
            <button
              type="button"
              onClick={handleResend}
              disabled={resendState === 'sending'}
              className="font-medium underline underline-offset-2 hover:text-amber-100 disabled:opacity-50"
            >
              {resendState === 'sending' ? 'Sending...' : 'Resend email'}
            </button>
          )}

          <button
            type="button"
            onClick={() => setBannerDismissed(true)}
            aria-label="Dismiss verification notice"
            className="p-1 rounded text-amber-500/80 hover:text-amber-200 hover:bg-amber-900/40 transition"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </>
  );
};
