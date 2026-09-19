import React from 'react';

interface Props {
  name: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const UserAvatar: React.FC<Props> = ({ name, size = 'md', className = '' }) => {
  const getInitials = (str: string) => {
    if (!str) return '?';
    const parts = str.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return str.slice(0, 2).toUpperCase();
  };

  const sizeClasses = {
    sm: 'w-6 h-6 text-[10px]',
    md: 'w-8 h-8 text-xs',
    lg: 'w-10 h-10 text-sm',
  }[size];

  // Deterministic neutral zinc background
  return (
    <div
      className={`rounded-md bg-zinc-800 text-zinc-100 font-semibold flex items-center justify-center select-none border border-zinc-700/60 shadow-sm flex-shrink-0 ${sizeClasses} ${className}`}
    >
      {getInitials(name)}
    </div>
  );
};
