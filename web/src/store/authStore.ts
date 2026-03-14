import { create } from "zustand";
import type { UserProfile } from "../types/auth";

interface AuthState {
  user: UserProfile | null;
  isAuthenticated: boolean;
  token: string | null;
  isLoading: boolean;
  setAuth: (user: UserProfile, token: string) => void;
  logout: () => void;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  token: null,
  isLoading: true,
  setAuth: (user, token) => {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user));
    set({ user, token, isAuthenticated: true, isLoading: false });
  },
  logout: () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    set({ user: null, token: null, isAuthenticated: false, isLoading: false });
  },
  hydrate: async () => {
    const token = localStorage.getItem("token");
    const userStr = localStorage.getItem("user");
    if (!token || !userStr) { set({ isLoading: false }); return; }
    try {
      const user: UserProfile = JSON.parse(userStr);
      set({ user, token, isAuthenticated: true, isLoading: false });
    } catch {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      set({ isLoading: false });
    }
  },
}));
