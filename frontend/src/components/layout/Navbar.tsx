import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { UserAvatar } from '../common/UserAvatar';
import { LogOut } from 'lucide-react';

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

  return (
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
              className="p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 rounded-md transition ml-1"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
};

