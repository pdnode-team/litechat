import React, { useEffect, useState } from 'react';
import { Clock, AlertTriangle, CheckCircle } from 'lucide-react';
import { parseUtcDate } from '../../utils/datetime';

interface Props {
  dueAt?: string;
  completedAt?: string;
  label?: string;
}

export const SlaCountdown: React.FC<Props> = ({ dueAt, completedAt, label = 'SLA' }) => {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 10000);
    return () => clearInterval(timer);
  }, []);

  if (completedAt) {
    const fulfilled = !dueAt || parseUtcDate(completedAt) <= parseUtcDate(dueAt);
    return (
      <div className={`inline-flex items-center text-[11px] font-mono font-medium px-2 py-0.5 rounded border ${fulfilled ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80' : 'bg-rose-950/60 text-rose-300 border-rose-800/80'}`}>
        <CheckCircle className="w-3 h-3 mr-1" />
        {label}: {fulfilled ? 'Fulfilled' : 'Breached'}
      </div>
    );
  }

  if (!dueAt) {
    return (
      <div className="inline-flex items-center text-[11px] font-mono text-zinc-500">
        <Clock className="w-3 h-3 mr-1" />
        {label}: N/A
      </div>
    );
  }

  const target = parseUtcDate(dueAt);
  const diffMs = target.getTime() - now.getTime();
  const isBreached = diffMs < 0;
  const absDiff = Math.abs(diffMs);

  const hours = Math.floor(absDiff / (1000 * 60 * 60));
  const minutes = Math.floor((absDiff % (1000 * 60 * 60)) / (1000 * 60));

  let timeText = '';
  if (hours > 24) {
    timeText = `${Math.floor(hours / 24)}d ${hours % 24}h`;
  } else if (hours > 0) {
    timeText = `${hours}h ${minutes}m`;
  } else {
    timeText = `${minutes}m`;
  }

  if (isBreached) {
    return (
      <div className="inline-flex items-center text-[11px] font-mono font-semibold px-2 py-0.5 rounded bg-rose-950/80 text-rose-300 border border-rose-800 animate-pulse">
        <AlertTriangle className="w-3 h-3 mr-1 text-rose-400" />
        {label}: -{timeText} (Breached)
      </div>
    );
  }

  const isUrgent = diffMs < 30 * 60 * 1000; // < 30 mins

  return (
    <div className={`inline-flex items-center text-[11px] font-mono font-medium px-2 py-0.5 rounded border ${isUrgent ? 'bg-amber-950/80 text-amber-300 border-amber-800' : 'bg-zinc-900 text-zinc-300 border-zinc-800'}`}>
      <Clock className={`w-3 h-3 mr-1 ${isUrgent ? 'text-amber-400' : 'text-zinc-500'}`} />
      {label}: {timeText} remaining
    </div>
  );
};
