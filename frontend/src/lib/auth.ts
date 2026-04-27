/**
 * AegisCX auth/session store.
 * Supports both real authenticated users and a local development guest session.
 */

import { create } from 'zustand';
import type { PersistStorage, StorageValue } from 'zustand/middleware';
import { persist } from 'zustand/middleware';
import { authApi } from './api';

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  company_id?: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isGuestSession: boolean;
  isLoading: boolean;
  hasBootstrapped: boolean;
  bootstrap: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; name: string; password: string; company_name?: string }) => Promise<void>;
  logout: () => void;
  loadMe: () => Promise<void>;
}

type PersistedAuthState = Pick<
  AuthState,
  'accessToken' | 'refreshToken' | 'isAuthenticated' | 'isGuestSession' | 'user'
>;

function getStoredToken(key: 'access_token' | 'refresh_token'): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function clearStoredTokens() {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  } catch {
    // Ignore storage cleanup failures so a bad browser state does not crash the app.
  }
}

const authStorage: PersistStorage<PersistedAuthState> = {
  getItem: (name) => {
    if (typeof window === 'undefined') {
      return null;
    }

    try {
      const rawValue = localStorage.getItem(name);
      if (!rawValue) {
        return null;
      }

      return JSON.parse(rawValue) as StorageValue<PersistedAuthState>;
    } catch {
      try {
        localStorage.removeItem(name);
      } catch {
        // Ignore cleanup failures and fall back to a fresh session.
      }
      return null;
    }
  },
  setItem: (name, value) => {
    if (typeof window === 'undefined') {
      return;
    }

    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch {
      // Ignore persistence failures and keep the in-memory session alive.
    }
  },
  removeItem: (name) => {
    if (typeof window === 'undefined') {
      return;
    }

    try {
      localStorage.removeItem(name);
    } catch {
      // Ignore persistence failures during logout/reset.
    }
  },
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isGuestSession: false,
      isLoading: false,
      hasBootstrapped: false,

      bootstrap: async () => {
        if (get().hasBootstrapped || get().isLoading) return;
        set({ isLoading: true });
        try {
          await get().loadMe();
        } catch {
          // A missing real session is fine here. The backend will provide a
          // guest session in local development when available.
        } finally {
          set({ isLoading: false, hasBootstrapped: true });
        }
      },

      login: async (email: string, password: string) => {
        set({ isLoading: true });
        try {
          const res = await authApi.login({ email, password });
          const { access_token, refresh_token } = res.data;

          if (typeof window !== 'undefined') {
            localStorage.setItem('access_token', access_token);
            localStorage.setItem('refresh_token', refresh_token);
          }

          set({
            accessToken: access_token,
            refreshToken: refresh_token,
            isAuthenticated: true,
            isGuestSession: false,
          });

          await get().loadMe();
          set({ hasBootstrapped: true });
        } finally {
          set({ isLoading: false });
        }
      },

      register: async (data: { email: string; name: string; password: string; company_name?: string }) => {
        set({ isLoading: true });
        try {
          const res = await authApi.register(data);
          const { access_token, refresh_token } = res.data;

          if (typeof window !== 'undefined') {
            localStorage.setItem('access_token', access_token);
            localStorage.setItem('refresh_token', refresh_token);
          }

          set({
            accessToken: access_token,
            refreshToken: refresh_token,
            isAuthenticated: true,
            isGuestSession: false,
          });

          await get().loadMe();
          set({ hasBootstrapped: true });
        } finally {
          set({ isLoading: false });
        }
      },

      logout: () => {
        clearStoredTokens();
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isGuestSession: false,
          hasBootstrapped: true,
        });
      },

      loadMe: async () => {
        const accessToken = getStoredToken('access_token');
        const refreshToken = getStoredToken('refresh_token');
        try {
          const res = await authApi.me();
          set({
            user: res.data,
            accessToken,
            refreshToken,
            isAuthenticated: true,
            isGuestSession: !accessToken,
          });
        } catch (error) {
          clearStoredTokens();
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
            isGuestSession: false,
          });
          throw error;
        }
      },
    }),
    {
      name: 'aegiscx-auth',
      storage: authStorage,
      version: 2,
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
        isGuestSession: state.isGuestSession,
        user: state.user,
      }),
    }
  )
);
