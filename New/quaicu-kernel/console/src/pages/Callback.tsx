// OIDC redirect landing page (/callback). Exchanges the authorization code for tokens, stores the
// id_token as the session bearer, then routes to the dashboard. Rendered outside the auth gate.

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { completeLogin } from "../oidc/oidc";

export default function Callback() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    completeLogin(window.location.search)
      .then(() => {
        if (!cancelled) navigate("/", { replace: true });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(String((e as Error)?.message ?? e));
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  if (error) {
    return (
      <div className="gate">
        <h2>Sign-in failed</h2>
        <p className="error">{error}</p>
        <p>
          <a href="/">← Back to the console</a>
        </p>
      </div>
    );
  }

  return (
    <div className="gate">
      <h2>Signing you in…</h2>
      <p className="muted">Completing the secure handshake with your identity provider.</p>
    </div>
  );
}
