import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Navbar } from '../layout/Navbar';
import { AgentWorkspace } from '../agent/AgentWorkspace';
import { AdminDashboard } from '../admin/AdminDashboard';
import { Inbox, Shield } from 'lucide-react';

export const StaffApp: React.FC = () => {
  const { user, canAccessAdmin } = useAuth();
  const [activeView, setActiveView] = useState<'inbox' | 'admin'>('inbox');

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-100 flex flex-col antialiased">
      <Navbar
        systemLabel="LITECHAT // STAFF WORKSPACE"
        badge={user?.role === 'admin' ? 'ADMIN' : 'AGENT'}
      >
        {canAccessAdmin && (
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-0.5 ml-4">
            <button
              type="button"
              onClick={() => setActiveView('inbox')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono rounded-md transition ${
                activeView === 'inbox'
                  ? 'bg-zinc-800 text-zinc-100 font-medium'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Inbox className="w-3.5 h-3.5" />
              <span>Inbox</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveView('admin')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono rounded-md transition ${
                activeView === 'admin'
                  ? 'bg-zinc-800 text-zinc-100 font-medium'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Shield className="w-3.5 h-3.5" />
              <span>Admin Console</span>
            </button>
          </div>
        )}
      </Navbar>

      <main className="flex-1 flex flex-col">
        {canAccessAdmin && activeView === 'admin' ? (
          <AdminDashboard />
        ) : (
          <AgentWorkspace />
        )}
      </main>
    </div>
  );
};
