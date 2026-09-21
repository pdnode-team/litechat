import React, { useEffect, useState } from 'react';
import { Clock } from 'lucide-react';
import { settingsApi } from '../../api/client';
import { AppSettings } from '../../types';
import { apiErrorMessage } from '../../utils/errors';
import { useToast } from '../common/Toast';

const inputClass =
  'w-full text-xs px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:border-zinc-600 focus:outline-none';
const labelClass = 'block text-[10px] font-mono uppercase text-zinc-500 mb-1';
const DAYS = [
  { id: 'mon', label: 'Mon' },
  { id: 'tue', label: 'Tue' },
  { id: 'wed', label: 'Wed' },
  { id: 'thu', label: 'Thu' },
  { id: 'fri', label: 'Fri' },
  { id: 'sat', label: 'Sat' },
  { id: 'sun', label: 'Sun' },
];

export const SlaSettingsPanel: React.FC = () => {
  const { showSuccess, showError } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    settingsApi
      .get()
      .then(setSettings)
      .catch((err) => showError(apiErrorMessage(err, 'Could not load SLA settings.')))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading || !settings) {
    return <p className="text-xs text-zinc-500 font-mono p-4">Loading SLA settings…</p>;
  }

  const selectedDays = new Set(settings.sla_weekdays.split(',').map((d) => d.trim()).filter(Boolean));
  const toggleDay = (id: string) => {
    const next = new Set(selectedDays);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSettings({
      ...settings,
      sla_weekdays: DAYS.map((d) => d.id).filter((d) => next.has(d)).join(','),
    });
  };

  const num = (key: keyof AppSettings, value: string) => {
    const parsed = Number(value);
    setSettings({ ...settings, [key]: Number.isFinite(parsed) ? parsed : 0 });
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await settingsApi.updateSla({
        sla_first_urgent: settings.sla_first_urgent,
        sla_first_high: settings.sla_first_high,
        sla_first_medium: settings.sla_first_medium,
        sla_first_low: settings.sla_first_low,
        sla_resolution_urgent: settings.sla_resolution_urgent,
        sla_resolution_high: settings.sla_resolution_high,
        sla_resolution_medium: settings.sla_resolution_medium,
        sla_resolution_low: settings.sla_resolution_low,
        sla_business_hours_enabled: settings.sla_business_hours_enabled,
        sla_weekdays: settings.sla_weekdays,
        sla_start: settings.sla_start,
        sla_end: settings.sla_end,
        sla_timezone: settings.sla_timezone,
        sla_observe_holidays: settings.sla_observe_holidays,
      });
      setSettings(updated);
      showSuccess('SLA settings saved. They apply to new tickets only.');
    } catch (err) {
      showError(apiErrorMessage(err, 'Could not save SLA settings.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="bg-zinc-900/50 rounded-xl border border-zinc-800 p-5 space-y-5 max-w-3xl">
      <div className="flex items-start gap-2">
        <Clock className="w-4 h-4 text-zinc-400 mt-0.5" />
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">SLA</h2>
          <p className="text-[11px] text-zinc-500">
            Changing these values does not rewrite deadlines on tickets that already exist.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {(['urgent', 'high', 'medium', 'low'] as const).map((priority) => (
          <div key={priority} className="space-y-2">
            <p className="text-[10px] font-mono uppercase text-zinc-500">{priority}</p>
            <label>
              <span className={labelClass}>First response (min)</span>
              <input
                type="number"
                min={1}
                value={settings[`sla_first_${priority}` as const]}
                onChange={(e) => num(`sla_first_${priority}`, e.target.value)}
                className={inputClass}
              />
            </label>
            <label>
              <span className={labelClass}>Resolution (min)</span>
              <input
                type="number"
                min={1}
                value={settings[`sla_resolution_${priority}` as const]}
                onChange={(e) => num(`sla_resolution_${priority}`, e.target.value)}
                className={inputClass}
              />
            </label>
          </div>
        ))}
      </div>

      <label className="flex items-start gap-2.5 cursor-pointer">
        <input
          type="checkbox"
          checked={settings.sla_business_hours_enabled}
          onChange={(e) => setSettings({ ...settings, sla_business_hours_enabled: e.target.checked })}
          className="mt-0.5 h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-950 accent-emerald-500"
        />
        <span>
          <span className="block text-xs text-zinc-200">Count only business hours</span>
          <span className="block text-[10px] font-mono text-zinc-500">
            When off, deadlines are calendar minutes (the original behaviour).
          </span>
        </span>
      </label>

      <div className="flex flex-wrap gap-2">
        {DAYS.map((day) => (
          <button
            key={day.id}
            type="button"
            onClick={() => toggleDay(day.id)}
            className={`px-2 py-1 text-[11px] font-mono rounded-md border ${
              selectedDays.has(day.id)
                ? 'bg-zinc-100 text-zinc-900 border-zinc-100'
                : 'bg-zinc-950 text-zinc-500 border-zinc-800'
            }`}
          >
            {day.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label>
          <span className={labelClass}>Start</span>
          <input type="time" value={settings.sla_start} onChange={(e) => setSettings({ ...settings, sla_start: e.target.value })} className={inputClass} />
        </label>
        <label>
          <span className={labelClass}>End</span>
          <input type="time" value={settings.sla_end} onChange={(e) => setSettings({ ...settings, sla_end: e.target.value })} className={inputClass} />
        </label>
        <label>
          <span className={labelClass}>Timezone</span>
          <input value={settings.sla_timezone} onChange={(e) => setSettings({ ...settings, sla_timezone: e.target.value })} className={inputClass} placeholder="UTC or Asia/Shanghai" />
        </label>
      </div>

      <label className="flex items-start gap-2.5 cursor-pointer opacity-70">
        <input type="checkbox" checked={settings.sla_observe_holidays} disabled className="mt-0.5 h-3.5 w-3.5" />
        <span className="text-[11px] text-zinc-500">Skip public holidays (not available yet; the flag is stored for later.)</span>
      </label>

      <button type="submit" disabled={saving} className="text-xs font-medium px-3 py-1.5 rounded-md bg-zinc-100 text-zinc-900 hover:bg-white disabled:opacity-50">
        {saving ? 'Saving…' : 'Save SLA'}
      </button>
    </form>
  );
};
