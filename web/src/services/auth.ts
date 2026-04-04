import type { UserProfile } from "../types/auth";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const API_V1 = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Core fetch wrapper with 401 interceptor
// ---------------------------------------------------------------------------

let isRefreshing = false;
let refreshPromise: Promise<boolean> | null = null;

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.headers) Object.assign(headers, options.headers);
  const base = endpoint.startsWith("/auth") ? API_BASE : API_V1;
  const response = await fetch(`${base}${endpoint}`, { ...options, headers });

  // 401 interceptor: attempt silent token refresh once
  if (response.status === 401 && token && !endpoint.includes("/auth/refresh") && !endpoint.includes("/auth/login")) {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      // Retry the original request with the new token
      const newToken = sessionStorage.getItem("token");
      if (newToken) headers["Authorization"] = `Bearer ${newToken}`;
      const retryResponse = await fetch(`${base}${endpoint}`, { ...options, headers });
      if (!retryResponse.ok) {
        const error = await retryResponse.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(error.detail || error.message || error.error || `API error ${retryResponse.status}`);
      }
      return retryResponse.json();
    }
    // Refresh failed — force logout
    forceLogout();
    throw new Error("Session expired. Please log in again.");
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || error.message || error.error || `API error ${response.status}`);
  }
  return response.json();
}

async function attemptRefresh(): Promise<boolean> {
  // Deduplicate concurrent refresh attempts
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }
  isRefreshing = true;
  refreshPromise = doRefresh();
  try {
    return await refreshPromise;
  } finally {
    isRefreshing = false;
    refreshPromise = null;
  }
}

async function doRefresh(): Promise<boolean> {
  try {
    const token = sessionStorage.getItem("token");
    if (!token) return false;
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
    if (!response.ok) return false;
    // Session extended on the server side — token stays the same (opaque session token)
    return true;
  } catch {
    return false;
  }
}

function forceLogout() {
  sessionStorage.removeItem("token");
  sessionStorage.removeItem("tenant_id");
  sessionStorage.removeItem("user_id");
  // Redirect to login
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

// ---------------------------------------------------------------------------
// Raw login response from the backend
// ---------------------------------------------------------------------------
interface LoginResponse {
  token: string;
  session_id: string;
  user_id: string;
  username: string;
  role: string;
  tenant_id: string;
  expires_at: string;
  // MFA challenge response
  mfa_required?: boolean;
  mfa_token?: string;
}

// ---------------------------------------------------------------------------
// Public auth API
// ---------------------------------------------------------------------------
export const authService = {
  login: async (
    username: string,
    password: string,
    tenant_id?: string
  ): Promise<{ access_token: string; user: UserProfile } | { mfa_required: true; mfa_token: string }> => {
    const resolved_tenant_id =
      tenant_id ||
      (import.meta.env.VITE_TENANT_ID as string | undefined) ||
      "demo";

    const raw = await apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password, tenant_id: resolved_tenant_id }),
    });

    // MFA challenge — don't create a session yet
    if (raw.mfa_required) {
      return { mfa_required: true, mfa_token: raw.mfa_token! };
    }

    // Full login — store token in sessionStorage (not localStorage — cleared on tab close)
    sessionStorage.setItem("token", raw.token);
    const user = await apiFetch<UserProfile>("/auth/me");

    sessionStorage.setItem("tenant_id", raw.tenant_id || resolved_tenant_id);
    sessionStorage.setItem("user_id", raw.user_id);

    return { access_token: raw.token, user };
  },

  getMe: () => apiFetch<UserProfile>("/auth/me"),

  logout: async () => {
    try {
      await apiFetch<void>("/auth/logout", { method: "POST" });
    } catch {
      // Best-effort — still clear local state
    }
    forceLogout();
  },

  /** Expose for components that need to make authenticated API calls */
  apiFetch,
};
