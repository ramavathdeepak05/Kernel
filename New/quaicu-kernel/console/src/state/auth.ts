// Minimal auth/session state persisted in localStorage. The kernel CONSUMES bearer tokens via its
// IdentityPort — the console does not mint them, so the operator pastes a token (and the tenant id).
// A tiny pub/sub lets components re-render when the session changes.

const TOKEN_KEY = "quaicu.token";
const TENANT_KEY = "quaicu.tenant";
const API_BASE_KEY = "quaicu.apiBase";

type Listener = () => void;
const listeners = new Set<Listener>();

export interface Session {
  token: string;
  tenant: string;
  apiBase: string; // "" → relative URLs (dev proxy handles /v1)
}

function readFromStorage(): Session {
  return {
    token: localStorage.getItem(TOKEN_KEY) ?? "",
    tenant: localStorage.getItem(TENANT_KEY) ?? "",
    apiBase: localStorage.getItem(API_BASE_KEY) ?? "",
  };
}

// Cached snapshot: useSyncExternalStore requires getSnapshot to return a STABLE reference until the
// data actually changes, otherwise React errors / infinite-loops (blank screen). We recompute the
// cache only inside setSession.
let cache: Session = readFromStorage();

export function getSession(): Session {
  return cache;
}

export function setSession(next: Partial<Session>): void {
  if (next.token !== undefined) localStorage.setItem(TOKEN_KEY, next.token);
  if (next.tenant !== undefined) localStorage.setItem(TENANT_KEY, next.tenant);
  if (next.apiBase !== undefined) localStorage.setItem(API_BASE_KEY, next.apiBase);
  cache = readFromStorage();
  listeners.forEach((l) => l());
}

export function isAuthenticated(): boolean {
  return cache.token.length > 0 && cache.tenant.length > 0;
}

// Sign out: drop the token + tenant (keep apiBase, a deployment setting). Used by the OIDC logout
// button and the token-paste "clear" affordance.
export function clearSession(): void {
  setSession({ token: "", tenant: "" });
}

export function subscribe(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}
