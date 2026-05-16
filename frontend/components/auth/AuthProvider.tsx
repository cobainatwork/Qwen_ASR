'use client';

import { createContext, ReactNode, useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'qwen-asr-token';

interface AuthContextValue {
  token: string | null;
  setToken: (token: string | null) => void;
  isAuthenticated: boolean;
}

export const AuthContext = createContext<AuthContextValue>({
  token: null,
  setToken: () => {},
  isAuthenticated: false,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);

  useEffect(() => {
    const stored = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
    if (stored) setTokenState(stored);
  }, []);

  const setToken = useCallback((next: string | null) => {
    setTokenState(next);
    if (typeof window === 'undefined') return;
    if (next === null) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, next);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ token, setToken, isAuthenticated: token !== null }}>
      {children}
    </AuthContext.Provider>
  );
}
