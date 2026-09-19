import React from 'react';
import { TicketStatus } from '../../types';

interface Props {
  status: TicketStatus;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<Props> = ({ status, size = 'sm' }) => {
  const styles: Record<TicketStatus, { bg: string; text: string; label: string; dot: string }> = {
    open: {
      bg: 'bg-emerald-950/50 text-emerald-400 border-emerald-800/60',
      text: 'Open',
      label: 'Open',
      dot: 'bg-emerald-400',
    },
    pending: {
      bg: 'bg-amber-950/50 text-amber-400 border-amber-800/60',
      text: 'Pending',
      label: 'Pending',
      dot: 'bg-amber-400',
    },
    in_progress: {
      bg: 'bg-blue-950/50 text-blue-400 border-blue-800/60',
      text: 'In Progress',
      label: 'In Progress',
      dot: 'bg-blue-400',
    },
    resolved: {
      bg: 'bg-purple-950/50 text-purple-400 border-purple-800/60',
      text: 'Resolved',
      label: 'Resolved',
      dot: 'bg-purple-400',
    },
    closed: {
      bg: 'bg-zinc-900 text-zinc-400 border-zinc-800',
      text: 'Closed',
      label: 'Closed',
      dot: 'bg-zinc-500',
    },
  };

  const current = styles[status] || styles.open;
  const sizeClasses = size === 'sm' ? 'text-[11px] px-2 py-0.5' : 'text-xs px-2.5 py-1';

  return (
    <span
      className={`inline-flex items-center font-mono font-medium rounded border ${current.bg} ${sizeClasses}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${current.dot}`} />
      {current.label}
    </span>
  );
};
