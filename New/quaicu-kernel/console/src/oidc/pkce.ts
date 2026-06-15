// PKCE (RFC 7636) + minimal JWT-claim helpers, built on the Web Crypto API — no dependencies.
//
// The challenge proves, at the token endpoint, that the client redeeming the code is the same one
// that started the flow, without a client secret. We never verify the id_token signature here (the
// kernel does that, authoritatively); decodeJwtPayload only reads the unverified tenant claim so the
// console knows which tenant to scope its API calls to.

function base64UrlEncode(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** A cryptographically random URL-safe string (used for the PKCE verifier and the state nonce). */
export function randomString(bytes = 48): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return base64UrlEncode(arr.buffer);
}

/** The S256 PKCE code challenge for a verifier: base64url(SHA-256(verifier)). */
export async function s256Challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64UrlEncode(digest);
}

/** Decode a JWT's payload segment (unverified) into a claims object. Returns {} on a malformed token. */
export function decodeJwtPayload(token: string): Record<string, unknown> {
  const segment = token.split(".")[1];
  if (!segment) return {};
  try {
    const b64 = segment.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(b64);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const json = new TextDecoder().decode(bytes);
    return json ? (JSON.parse(json) as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}
