import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User } from '../types';
import { authApi, setUnauthorizedHandler } from '../api/client';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  canAccessAdmin: boolean;
  login: (usernameOrEmail: string, pass: string) => Promise<void>;
  register: (email: string, username: string, fullName: string, pass: string) => Promise<void>;
  setupAdmin: (email: string, username: string, fullName: string, pass: string) => Promise<void>;
  /** Re-read the profile; used when the account changes server-side. */
  refreshUser: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const logout = useCallback(() => {
    localStorage.removeItem('litechat_token');
    setUser(null);
  }, []);

  // The axios response interceptor lives outside React, so hand it a logout
  // callback. Without this a 401 would clear localStorage but leave the SPA
  // rendering a logged-in shell whose every request fails.
  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Initialize: verify the stored token before trusting it.
  useEffect(() => {
    const initAuth = async () => {
      if (localStorage.getItem('litechat_token')) {
        try {
          setUser(await authApi.getMe());
        } catch {
          localStorage.removeItem('litechat_token');
          setUser(null);
        }
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  const persistSession = (accessToken: string, nextUser: User) => {
    localStorage.setItem('litechat_token', accessToken);
    setUser(nextUser);
  };

  const login = async (usernameOrEmail: string, pass: string) => {
    const data = await authApi.login(usernameOrEmail, pass);
    persistSession(data.access_token, data.user);
  };

  const register = async (email: string, username: string, fullName: string, pass: string) => {
    const data = await authApi.register(email, username, fullName, pass);
    persistSession(data.access_token, data.user);
  };

  const setupAdmin = async (email: string, username: string, fullName: string, pass: string) => {
    const data = await authApi.setupAdmin(email, username, fullName, pass);
    persistSession(data.access_token, data.user);
  };

  const refreshUser = useCallback(async () => {
    if (!localStorage.getItem('litechat_token')) return;
    try {
      setUser(await authApi.getMe());
    } catch {
      // A failed refresh is handled by the 401 interceptor.
    }
  }, []);

  const canAccessAdmin = user?.role === 'admin';

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        canAccessAdmin,
        login,
        register,
        setupAdmin,
        refreshUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
