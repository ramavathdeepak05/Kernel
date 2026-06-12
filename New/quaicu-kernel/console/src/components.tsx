// Small shared UI primitives + an async data hook. Plain styling (see styles.css).

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api/client";

export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(() => {
    setLoading(true);
    setError(null);
    fn()
      .then((d) => setData(d))
      .catch((e) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(run, [run]);
  return { data, loading, error, reload: run };
}

export function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <div className="card-title">{title}</div>
      <div className="card-body">{children}</div>
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

const DECISION_CLASS: Record<string, string> = {
  allow: "badge-allow",
  deny: "badge-deny",
  require_approval: "badge-warn",
  APPROVED: "badge-allow",
  REJECTED: "badge-deny",
  PENDING: "badge-warn",
  TIMED_OUT: "badge-deny",
  ACTIVATED: "badge-allow",
  DRAFT: "badge-muted",
  REVIEW: "badge-warn",
  DEPRECATED: "badge-muted",
};

export function Badge({ value }: { value: string }) {
  return <span className={`badge ${DECISION_CLASS[value] ?? "badge-muted"}`}>{value}</span>;
}

export function Loading({ what }: { what?: string }) {
  return <div className="muted">Loading{what ? ` ${what}` : ""}…</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="error-box">⚠ {message}</div>;
}

export function Empty({ message }: { message: string }) {
  return <div className="muted empty">{message}</div>;
}
