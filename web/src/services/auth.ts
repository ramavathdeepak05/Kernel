import type { UserProfile } from "../types/auth";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const API_V1 = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("token");
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as object | undefined),
  };
  const base = endpoint.startsWith("/auth") ? API_BASE : API_V1;
  const response = await fetch(`${base}${endpoint}`, { ...options, headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || error.message || `API error ${response.status}`);
  }
  return response.json();
}

// Raw login response from the backend
interface LoginResponse {
  token: string;
  session_id: string;
  user_id: string;
  username: string;
  role: string;
  tenant_id: string;
  expires_at: string;
}

export const authService = {
  login: async (
    username: string,
    password: string,
    tenant_id = "demo"
  ): Promise<{ access_token: string; user: UserProfile }> => {
    const raw = await apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password, tenant_id }),
    });
    // Fetch full profile after login
    localStorage.setItem("token", raw.token);
    const user = await apiFetch<UserProfile>("/auth/me");
    localStorage.removeItem("token"); // let authStore handle persistence
    return { access_token: raw.token, user };
  },

  getMe: () => apiFetch<UserProfile>("/auth/me"),

  logout: () =>
    apiFetch<void>("/auth/logout", { method: "POST" }).catch(() => {}),
};
