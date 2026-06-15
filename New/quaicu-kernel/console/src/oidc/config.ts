// OIDC client configuration, read from Vite env vars (build- or runtime-injected). The console is a
// public SPA, so it uses Authorization Code + PKCE — there is NO client secret in the browser.
//
// Required to enable OIDC login:
//   VITE_OIDC_ISSUER       e.g. https://dev-123.okta.com/oauth2/default
//   VITE_OIDC_CLIENT_ID    the SPA application's client id
// Optional:
//   VITE_OIDC_REDIRECT_URI    default `${origin}/callback`
//   VITE_OIDC_SCOPES          default "openid profile email"
//   VITE_OIDC_AUTH_ENDPOINT   skip discovery: explicit authorization endpoint
//   VITE_OIDC_TOKEN_ENDPOINT  skip discovery: explicit token endpoint
//   VITE_OIDC_TENANT_CLAIM    id_token claim carrying the tenant id (default "tenant", falls back to "tid")
//
// The id_token obtained here is sent to the kernel as the bearer token; the kernel's OIDC
// IdentityPort (adapters/identity/oidc.py) cryptographically verifies it (issuer + audience + JWKS).
// The configured kernel audience must equal this client id.

export interface OidcConfig {
  issuer: string;
  clientId: string;
  redirectUri: string;
  scopes: string;
  authorizationEndpoint?: string;
  tokenEndpoint?: string;
  tenantClaim: string;
}

export function oidcConfig(): OidcConfig | null {
  const issuer = import.meta.env.VITE_OIDC_ISSUER;
  const clientId = import.meta.env.VITE_OIDC_CLIENT_ID;
  if (!issuer || !clientId) return null; // OIDC not configured → token-paste fallback only

  return {
    issuer: issuer.replace(/\/+$/, ""),
    clientId,
    redirectUri: import.meta.env.VITE_OIDC_REDIRECT_URI ?? `${window.location.origin}/callback`,
    scopes: import.meta.env.VITE_OIDC_SCOPES ?? "openid profile email",
    authorizationEndpoint: import.meta.env.VITE_OIDC_AUTH_ENDPOINT,
    tokenEndpoint: import.meta.env.VITE_OIDC_TOKEN_ENDPOINT,
    tenantClaim: import.meta.env.VITE_OIDC_TENANT_CLAIM ?? "tenant",
  };
}
