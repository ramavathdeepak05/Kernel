// Per-tier UI gating state. After the operator authenticates, the console fetches
// GET /v1/me/entitlements once and exposes the result to the whole tree. Feature flags come from the
// kernel's TIER_MATRIX (single source of truth) — the console never hard-codes tier→feature mappings.

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Entitlements } from "../api/types";
import { getSession, subscribe } from "./auth";

interface EntitlementsState {
  data: Entitlements | null;
  loading: boolean;
  error: string | null;
}

const EntitlementsContext = createContext<EntitlementsState>({
  data: null,
  loading: false,
  error: null,
});

export function EntitlementsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<EntitlementsState>({ data: null, loading: false, error: null });

  useEffect(() => {
    let cancelled = false;

    function load() {
      const { token, tenant } = getSession();
      if (!token || !tenant) {
        setState({ data: null, loading: false, error: null });
        return;
      }
      setState((s) => ({ ...s, loading: true }));
      api
        .entitlements()
        .then((data) => {
          if (!cancelled) setState({ data, loading: false, error: null });
        })
        .catch((e: unknown) => {
          if (!cancelled) {
            setState({ data: null, loading: false, error: String((e as Error)?.message ?? e) });
          }
        });
    }

    load();
    const unsub = subscribe(load); // re-fetch on sign-in / sign-out / tenant change
    return () => {
      cancelled = true;
      unsub();
    };
  }, []);

  return <EntitlementsContext.Provider value={state}>{children}</EntitlementsContext.Provider>;
}

export function useEntitlements(): EntitlementsState {
  return useContext(EntitlementsContext);
}

/**
 * Whether a tier-gated feature is enabled. Defaults to `true` while entitlements are loading or
 * unavailable so the UI never flashes features hidden (gating tightens once the data arrives; the
 * kernel still fail-closes server-side regardless of what the console shows).
 */
export function useFeature(name: string): boolean {
  const { data } = useEntitlements();
  if (!data) return true;
  return data.features[name] ?? true;
}
