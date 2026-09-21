import React, { useEffect, useState } from 'react';
import { Mail, Save, Send, ServerCog, BellRing } from 'lucide-react';
import { settingsApi } from '../../api/client';
import { AppSettings } from '../../types';
import { apiErrorMessage } from '../../utils/errors';
import { useToast } from '../common/Toast';

const inputClass =
  'w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:border-zinc-600 focus:outline-none transition';
const labelClass = 'block text-[10px] font-mono uppercase text-zinc-500 mb-1';

const Toggle: React.FC<{
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: string;
}> = ({ checked, onChange, label, hint }) => (
  <label className="flex items-start gap-2.5 py-1.5 cursor-pointer">
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="mt-0.5 h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-950 accent-emerald-500"
    />
    <span>
      <span className="block text-xs text-zinc-200">{label}</span>
      {hint && <span className="block text-[10px] font-mono text-zinc-500">{hint}</span>}
    </span>
  </label>
);

/**
 * SMTP and notification configuration, editable at runtime.
 *
 * Values are stored in the database, so an administrator can change them
 * without touching the server's environment. Environment variables remain the
 * fallback for anything never saved here.
 */
export const EmailSettingsPanel: React.FC = () => {
  const { showSuccess, showError } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [password, setPassword] = useState('');
  const [testTo, setTestTo] = useState('');
  const [testing, setTesting] = useState(false);
  const [savedSnapshot, setSavedSnapshot] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    settingsApi
      .get()
      .then((data) => {
        if (cancelled) return;
        setSettings(data);
        setSavedSnapshot(JSON.stringify({ ...data, smtp_password_set: data.smtp_password_set }));
        setTestTo(data.smtp_from);
      })
      .catch((err) => {
        if (!cancelled) showError(apiErrorMessage(err, 'Could not load settings.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const patch = (changes: Partial<AppSettings>) => {
    setSettings((prev) => (prev ? { ...prev, ...changes } : prev));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await settingsApi.updateEmail({
        smtp_enabled: settings.smtp_enabled,
        smtp_host: settings.smtp_host,
        smtp_port: settings.smtp_port,
        smtp_username: settings.smtp_username,
        smtp_use_tls: settings.smtp_use_tls,
        smtp_from: settings.smtp_from,
        public_app_url: settings.public_app_url,
        // Only send the password when the admin typed a new one.
        ...(password ? { smtp_password: password } : {}),
      });
      const withNotifications = await settingsApi.updateNotifications({
        notify_new_ticket: settings.notify_new_ticket,
        notify_ticket_reply: settings.notify_ticket_reply,
        notify_assignment: settings.notify_assignment,
        notify_status_change: settings.notify_status_change,
        support_email: settings.support_email,
      });
      setSettings(withNotifications);
      setSavedSnapshot(JSON.stringify({ ...withNotifications, smtp_password_set: withNotifications.smtp_password_set }));
      void updated;
      setPassword('');
      showSuccess('Settings saved');
    } catch (err) {
      showError(apiErrorMessage(err, 'Could not save the settings.'));
    } finally {
      setSaving(false);
    }
  };

  const smtpDirty =
    Boolean(password) ||
    (settings !== null && JSON.stringify({ ...settings, smtp_password_set: settings.smtp_password_set }) !== savedSnapshot);

  const handleTest = async () => {
    if (!testTo.trim() || smtpDirty) return;
    setTesting(true);
    try {
      const result = await settingsApi.sendTestEmail(testTo.trim());
      if (result.sent) showSuccess(result.detail);
      else showError(result.detail);
    } catch (err) {
      showError(apiErrorMessage(err, 'The test email could not be sent.'));
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-12 text-center text-xs font-mono text-zinc-500">Loading settings...</div>
    );
  }

  if (!settings) {
    return (
      <div className="p-12 text-center text-xs font-mono text-rose-300">
        Settings could not be loaded.
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className="space-y-4">
      {/* SMTP */}
      <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 overflow-hidden">
        <div className="p-3.5 border-b border-zinc-800 bg-zinc-900/40 flex items-center gap-2">
          <ServerCog className="w-3.5 h-3.5 text-zinc-400" />
          <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
            Outbound email (SMTP)
          </h2>
        </div>

        <div className="p-4 space-y-3">
          <p className="text-[11px] text-zinc-400">
            Leave the host empty to disable email; links such as password resets are then written to
            the server log instead.
          </p>

          <Toggle
            checked={settings.smtp_enabled}
            onChange={(next) => patch({ smtp_enabled: next })}
            label="Send email"
            hint="Turn off to keep every notification in the log only."
          />

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className={labelClass}>SMTP host</label>
              <input
                type="text"
                value={settings.smtp_host}
                onChange={(e) => patch({ smtp_host: e.target.value })}
                placeholder="smtp.example.com"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Port</label>
              <input
                type="number"
                min={1}
                max={65535}
                value={settings.smtp_port}
                onChange={(e) => patch({ smtp_port: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Username</label>
              <input
                type="text"
                value={settings.smtp_username}
                onChange={(e) => patch({ smtp_username: e.target.value })}
                placeholder="apikey"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={settings.smtp_password_set ? '•••••••• (stored)' : 'not set'}
                className={inputClass}
              />
              <p className="mt-1 text-[10px] font-mono text-zinc-500">
                Stored encrypted; leave blank to keep the current value.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>From address</label>
              <input
                type="text"
                value={settings.smtp_from}
                onChange={(e) => patch({ smtp_from: e.target.value })}
                placeholder="no-reply@example.com"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>App base URL</label>
              <input
                type="text"
                value={settings.public_app_url}
                onChange={(e) => patch({ public_app_url: e.target.value })}
                placeholder="https://support.example.com"
                className={inputClass}
              />
              <p className="mt-1 text-[10px] font-mono text-zinc-500">
                Used to build the links inside notification emails.
              </p>
            </div>
          </div>

          <Toggle
            checked={settings.smtp_use_tls}
            onChange={(next) => patch({ smtp_use_tls: next })}
            label="Use STARTTLS"
            hint="Enable for port 587; leave off for implicit-TLS port 465."
          />

          <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-zinc-800">
            <div className="flex-1 min-w-[200px]">
              <label className={labelClass}>Send a test message to</label>
              <div className="relative">
                <Mail className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="email"
                  value={testTo}
                  onChange={(e) => setTestTo(e.target.value)}
                  placeholder="you@example.com"
                  className={`${inputClass} pl-8`}
                />
              </div>
            </div>
            <button
              type="button"
              onClick={handleTest}
              disabled={testing || !testTo.trim() || smtpDirty}
              title={smtpDirty ? 'Save the SMTP settings before sending a test.' : undefined}
              className="px-3 py-2 text-xs font-medium rounded-lg border border-zinc-700 text-zinc-200 hover:bg-zinc-800 transition disabled:opacity-40 flex items-center gap-1.5"
            >
              <Send className="w-3.5 h-3.5" />
              {testing ? 'Sending...' : 'Send test'}
            </button>
          </div>
        </div>
      </div>

      {/* Notification policy */}
      <div className="bg-zinc-900/50 rounded-xl border border-zinc-800 overflow-hidden">
        <div className="p-3.5 border-b border-zinc-800 bg-zinc-900/40 flex items-center gap-2">
          <BellRing className="w-3.5 h-3.5 text-zinc-400" />
          <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
            Who gets notified
          </h2>
        </div>

        <div className="p-4 space-y-1">
          <Toggle
            checked={settings.notify_new_ticket}
            onChange={(next) => patch({ notify_new_ticket: next })}
            label="New ticket"
            hint="Email every active agent and administrator when a ticket is opened."
          />
          <Toggle
            checked={settings.notify_ticket_reply}
            onChange={(next) => patch({ notify_ticket_reply: next })}
            label="New reply"
            hint="Support replies email the customer; customer replies email the assignee (or all staff)."
          />
          <Toggle
            checked={settings.notify_assignment}
            onChange={(next) => patch({ notify_assignment: next })}
            label="Assignment"
            hint="Email the agent a ticket is assigned to."
          />
          <Toggle
            checked={settings.notify_status_change}
            onChange={(next) => patch({ notify_status_change: next })}
            label="Resolved or closed"
            hint="Email the customer when their ticket is resolved or closed."
          />

          <div className="pt-2">
            <label className={labelClass}>Support inbox (optional)</label>
            <input
              type="text"
              value={settings.support_email}
              onChange={(e) => patch({ support_email: e.target.value })}
              placeholder="support@example.com"
              className={inputClass}
            />
            <p className="mt-1 text-[10px] font-mono text-zinc-500">
              Receives new-ticket and unassigned-reply notifications in addition to staff accounts.
            </p>
          </div>

          <p className="pt-2 text-[10px] font-mono text-zinc-500">
            Internal notes (whispers) never generate email.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={saving}
          className="px-3.5 py-2 text-xs font-semibold rounded-lg bg-zinc-100 hover:bg-white text-zinc-950 transition disabled:opacity-50 flex items-center gap-1.5"
        >
          <Save className="w-3.5 h-3.5" />
          {saving ? 'Saving...' : 'Save settings'}
        </button>
      </div>
    </form>
  );
};
