/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useState } from 'react';
import { api, clearAccessToken, getAccessToken, setAccessToken } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getAccessToken()));

  const logout = () => {
    clearAccessToken();
    setUser(null);
    setLoading(false);
  };

  const authenticate = async (method, credentials) => {
    const result = await api[method](credentials);
    setAccessToken(result.access_token);
    setUser(result.user);
    return result.user;
  };

  useEffect(() => {
    const restore = async () => {
      if (!getAccessToken()) return setLoading(false);
      try {
        setUser(await api.me());
      } catch {
        clearAccessToken();
      } finally {
        setLoading(false);
      }
    };
    restore();
    window.addEventListener('auth:expired', logout);
    return () => window.removeEventListener('auth:expired', logout);
  }, []);

  return <AuthContext.Provider value={{ user, loading, authenticate, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
