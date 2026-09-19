import React from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RealtimeProvider } from './context/RealtimeContext';
import { AuthView } from './components/auth/AuthView';
import { PasswordRecoveryGate, hasRecoveryToken } from './components/auth/PasswordRecoveryView';
import { ToastProvider } from './components/common/Toast';
import { CustomerApp } from './components/customer/CustomerApp';
import { StaffApp } from './components/staff/StaffApp';

const RootContent: React.FC = () => {
  const { user, loading } = useAuth();

  // An emailed reset/verification link lands here with a token in the URL. It
  // takes priority over whatever session state exists.
  if (hasRecoveryToken()) {
    return <PasswordRecoveryGate />;
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
