import React from 'react';
import { TicketPriority } from '../../types';

interface Props {
  priority: TicketPriority;
}

export const PriorityChip: React.FC<Props> = ({ priority }) => {
  const styles: Record<TicketPriority, { bg: string; dot: string; label: string }> = {
    urgent: {
      bg: 'bg-rose-950/60 border-rose-800/80 text-rose-300',
      dot: 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]',
      label: 'Urgent',
    },
    high: {
      bg: 'bg-orange-950/60 border-orange-800/80 text-orange-300',
      dot: 'bg-orange-500',
      label: 'High',
    },
    medium: {
      bg: 'bg-zinc-900 border-zinc-800 text-zinc-300',
      dot: 'bg-zinc-400',
      label: 'Medium',
    },
    low: {
      bg: 'bg-zinc-900/60 border-zinc-800/60 text-zinc-500',
      dot: 'bg-zinc-600',
      label: 'Low',
    },
  };

  const config = styles[priority] || styles.medium;

  return (
    <span
      className={`inline-flex items-center text-[11px] font-mono font-medium px-2 py-0.5 rounded border ${config.bg}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${config.dot}`} />
      {config.label}
    </span>
  );
};
