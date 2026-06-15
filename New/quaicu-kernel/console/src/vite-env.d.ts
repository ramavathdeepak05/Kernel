/// <reference types="vite/client" />

// Typed access to the OIDC configuration injected at build/runtime via Vite env vars. All are
// optional: when VITE_OIDC_ISSUER / VITE_OIDC_CLIENT_ID are unset, the console falls back to
// manual token-paste (dev) and the "Sign in with your IdP" button is hidden.
interface ImportMetaEnv {
  readonly VITE_OIDC_ISSUER?: string;
  readonly VITE_OIDC_CLIENT_ID?: string;
  readonly VITE_OIDC_REDIRECT_URI?: string;
  readonly VITE_OIDC_SCOPES?: string;
  readonly VITE_OIDC_AUTH_ENDPOINT?: string;
  readonly VITE_OIDC_TOKEN_ENDPOINT?: string;
  readonly VITE_OIDC_TENANT_CLAIM?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
