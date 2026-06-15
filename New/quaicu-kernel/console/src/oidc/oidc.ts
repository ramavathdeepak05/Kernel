// The OIDC Authorization Code + PKCE flow, end to end.
//
//   beginLogin()    → discover endpoints, mint a PKCE verifier + state, redirect to the IdP.
//   completeLogin() → on the /callback, validate state, exchange the code (+ verifier) for tokens,
//                     read the tenant claim, and store the id_token as the session bearer.
//
// The id_token becomes the bearer the kernel verifies (issuer/audience/JWKS) on every API call.

import { oidcConfig, type OidcConfig } from "./config";
import { decodeJwtPayload, randomString, s256Challenge } from "./pkce";
import { setSession } from "../state/auth";

const VERIFIER_KEY = "quaicu.oidc.verifier";
const STATE_KEY = "quaicu.oidc.state";

/** True when the build is configured with an issuer + client id (OIDC login is available). */
export function oidcEnabled(): boolean {
  return oidcConfig() !== null;
}

interface Endpoints {
  authorization_endpoint: string;
  token_endpoint: string;
}

async function discover(cfg: OidcConfig): Promise<Endpoints> {
  if (cfg.authorizationEndpoint && cfg.tokenEndpoint) {
    return { authorization_endpoint: cfg.authorizationEndpoint, token_endpoint: cfg.tokenEndpoint };
  }
  const resp = await fetch(`${cfg.issuer}/.well-known/openid-configuration`);
  if (!resp.ok) throw new Error(`OIDC discovery failed (${resp.status}) at ${cfg.issuer}`);
  const doc = (await resp.json()) as Partial<Endpoints>;
  if (!doc.authorization_endpoint || !doc.token_endpoint) {
    throw new Error("OIDC discovery document is missing authorization/token endpoints");
  }
  return { authorization_endpoint: doc.authorization_endpoint, token_endpoint: doc.token_endpoint };
}

/** Start the login: redirect the browser to the IdP's authorization endpoint. */
export async function beginLogin(): Promise<void> {
  const cfg = oidcConfig();
  if (!cfg) throw new Error("OIDC is not configured (set VITE_OIDC_ISSUER and VITE_OIDC_CLIENT_ID)");

  const { authorization_endpoint } = await discover(cfg);
  const verifier = randomString();
  const state = randomString(16);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: cfg.clientId,
    redirect_uri: cfg.redirectUri,
    scope: cfg.scopes,
    state,
    code_challenge: await s256Challenge(verifier),
    code_challenge_method: "S256",
  });
  window.location.assign(`${authorization_endpoint}?${params.toString()}`);
}

/** Finish the login from the /callback query string. Throws with a human message on any failure. */
export async function completeLogin(search: string): Promise<void> {
  const cfg = oidcConfig();
  if (!cfg) throw new Error("OIDC is not configured");

  const params = new URLSearchParams(search);
  const idpError = params.get("error");
  if (idpError) {
    throw new Error(`IdP returned an error: ${idpError} ${params.get("error_description") ?? ""}`.trim());
  }

  const code = params.get("code");
  const state = params.get("state");
  const expectedState = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(VERIFIER_KEY);

  if (!code) throw new Error("No authorization code in the callback");
  if (!state || state !== expectedState) throw new Error("State mismatch — possible CSRF; aborting");
  if (!verifier) throw new Error("Missing PKCE verifier (session expired) — please retry sign-in");

  const { token_endpoint } = await discover(cfg);
  const resp = await fetch(token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: cfg.redirectUri,
      client_id: cfg.clientId,
      code_verifier: verifier,
    }).toString(),
  });
  if (!resp.ok) {
    throw new Error(`Token exchange failed (${resp.status}): ${await resp.text()}`);
  }

  const tokens = (await resp.json()) as { id_token?: string };
  if (!tokens.id_token) throw new Error("The IdP returned no id_token");

  const claims = decodeJwtPayload(tokens.id_token);
  const tenant = (claims[cfg.tenantClaim] ?? claims["tid"]) as string | undefined;
  if (!tenant) {
    throw new Error(`id_token has no '${cfg.tenantClaim}' (or 'tid') claim — cannot determine the tenant`);
  }

  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  // The kernel's OIDC IdentityPort cryptographically verifies this token; we only read the tenant.
  setSession({ token: tokens.id_token, tenant: String(tenant) });
}
