import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RealtimeProvider } from './context/RealtimeContext';
import { AuthView } from './components/auth/AuthView';
import {
  PasswordRecoveryGate,
  hasRecoveryToken,
  takeRecoveryTokens,
  type RecoveryTokens,
} from './components/auth/PasswordRecoveryView';
import { ToastProvider } from './components/common/Toast';
import { CustomerApp } from './components/customer/CustomerApp';
import { StaffApp } from './components/staff/StaffApp';

const RootContent: React.FC = () => {
  const { user, loading } = useAuth();
  // Capture the emailed token once. The gate strips it from the URL, so later
  // re-renders (auth init finishing) must not look at the address bar again.
  const [recovery] = useState<RecoveryTokens | null>(() =>
    hasRecoveryToken() ? takeRecoveryTokens() : null,
  );

  if (recovery?.reset || recovery?.verify || recovery?.emailChange) {
    return <PasswordRecoveryGate tokens={recovery} />;
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center text-zinc-400">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-xs uppercase tracking-wider font-mono">Initializing LiteChat...</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return <AuthView />;
  }

  if (user.role === 'customer') {
    return <CustomerApp />;
  }

  return <StaffApp />;
};

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <RealtimeProvider>
          <RootContent />
        </RealtimeProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
