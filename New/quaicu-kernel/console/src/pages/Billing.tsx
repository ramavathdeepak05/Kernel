import { useState } from "react";
import { api } from "../api/client";
import { Card, ErrorBox, Loading } from "../components";
import { useEntitlements } from "../state/entitlements";

// Commercial tiers, low → high. Upgrade targets are the tiers above the current one.
const TIER_ORDER = ["STARTER", "BUSINESS", "ENTERPRISE"];

function upgradeTargets(tier: string | null, status: string | null): string[] {
  // No active plan (unpaid / suspended) → offer the paid tiers from the bottom up.
  if (status === "NO_ACTIVE_PLAN" || !tier) return ["BUSINESS", "ENTERPRISE"];
  const idx = TIER_ORDER.indexOf(tier);
  return idx < 0 ? [] : TIER_ORDER.slice(idx + 1);
}

export default function Billing() {
  const { data, loading } = useEntitlements();
  const providers = data?.billing_providers ?? [];
  const [chosen, setChosen] = useState("");
  const provider = chosen || providers[0] || "";
  const [busyTier, setBusyTier] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Banner after returning from the provider's hosted page.
  const params = new URLSearchParams(window.location.search);
  const justUpgraded = params.get("upgraded") === "1";
  const justCancelled = params.get("cancelled") === "1";

  async function upgrade(tier: string) {
    setBusyTier(tier);
    setError(null);
    const origin = window.location.origin;
    try {
      const resp = await api.checkout({
        provider,
        tier,
        success_url: `${origin}/billing?upgraded=1`,
        cancel_url: `${origin}/billing?cancelled=1`,
      });
      window.location.assign(resp.url); // redirect to the provider's payment page
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
      setBusyTier(null);
    }
  }

  const targets = upgradeTargets(data?.tier ?? null, data?.status ?? null);

  return (
    <div className="page">
      <h1>Billing &amp; plan</h1>

      {justUpgraded && (
        <div className="notice">
          Payment received. Your plan updates as soon as the provider confirms — the kernel flips your
          tier from the billing webhook.
        </div>
      )}
      {justCancelled && <div className="error-box">Checkout cancelled — no change to your plan.</div>}

      <Card title="Current plan">
        {loading ? (
          <Loading />
        ) : (
          <p>
            {data?.tier ? (
              <span className={`tier-badge tier-${data.tier.toLowerCase()}`}>{data.tier}</span>
            ) : (
              <span className="muted">
                {data?.status === "NO_ACTIVE_PLAN" ? "No active plan" : "Not tier-limited"}
              </span>
            )}
          </p>
        )}
      </Card>

      <Card title="Upgrade">
        {providers.length === 0 ? (
          <p className="muted">Self-serve billing isn't enabled for this deployment.</p>
        ) : targets.length === 0 ? (
          <p className="muted">You're on the top tier — nothing to upgrade.</p>
        ) : (
          <>
            {providers.length > 1 && (
              <label className="inline">
                Pay with
                <select value={provider} onChange={(e) => setChosen(e.target.value)}>
                  {providers.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </label>
            )}
            <div className="plan-options">
              {targets.map((tier) => (
                <button
                  key={tier}
                  className="primary"
                  disabled={busyTier !== null}
                  onClick={() => upgrade(tier)}
                >
                  {busyTier === tier ? "Redirecting…" : `Upgrade to ${tier}`}
                </button>
              ))}
            </div>
            {error && <ErrorBox message={error} />}
          </>
        )}
      </Card>
    </div>
  );
}
