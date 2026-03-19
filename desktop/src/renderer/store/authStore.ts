import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  id: string
  full_name: string
  email: string
  role: string
}

export interface AuthState {
  token: string | null
  tenantId: string | null
  user: User | null
  setAuth: (token: string, tenantId: string, user: User) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set: (partial: Partial<AuthState>) => void) => ({
      token: null,
      tenantId: null,
      user: null,
      setAuth: (token: string, tenantId: string, user: User) => set({ token, tenantId, user }),
      logout: () => set({ token: null, tenantId: null, user: null }),
    }),
    { name: 'alis-auth' },
  ),
)
