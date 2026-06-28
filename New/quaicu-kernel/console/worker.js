// Cloudflare Worker entry for the console (Workers Static Assets).
//
// Single origin, no CORS: the browser calls same-origin /v1/... and this Worker reverse-proxies it
// to the Cloud Run kernel (the Worker->Cloud Run hop is server-side, so the browser never makes a
// cross-origin request). Every other path is served from the static SPA bundle (env.ASSETS), with
// SPA fallback for client-side routes (configured in wrangler.toml).
//
// Host header: dropped so the Workers runtime sets it to the Cloud Run origin host — Cloud Run
// routes by hostname and 404s a foreign Host. Update KERNEL_ORIGIN if the kernel moves.

const KERNEL_ORIGIN = "https://quaicu-kernel-152046316624.us-central1.run.app";

// Content-Security-Policy for the console document + assets. Baseline is self-only; the *only*
// permitted third party is Razorpay Checkout (the hosted, PCI-compliant payment widget loaded lazily
// by src/razorpay.ts — script + the api.razorpay.com iframe + *.razorpay.com telemetry/images).
//   • 'unsafe-inline' on style-src: React `style={{…}}` attributes + the Razorpay widget inject inline
//     styles. No inline *scripts* are allowed (script-src has no 'unsafe-inline').
//   • No COOP/COEP: those would block Razorpay's cross-origin iframe postMessage and break checkout.
//   • OIDC SSO (optional, per-deployment): if VITE_OIDC_ISSUER is set, add that issuer origin to
//     connect-src — it's not enumerated here because the hosted console signs up via password+Razorpay.
const CSP = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "script-src 'self' https://checkout.razorpay.com",
  "frame-src https://api.razorpay.com https://checkout.razorpay.com",
  "connect-src 'self' https://*.razorpay.com",
  "img-src 'self' data: https://*.razorpay.com",
  "font-src 'self'",
  "style-src 'self' 'unsafe-inline'",
].join("; ");

// Docs CSP: wider than the console — allows Google Fonts (MkDocs Material) and CDN scripts (Mermaid).
const DOCS_CSP = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
  "connect-src 'self'",
  "img-src 'self' data:",
  "font-src 'self' https://fonts.gstatic.com",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
].join("; ");

// Applied to every static-asset / SPA-document response. (frame-ancestors in the CSP is the modern
// clickjacking control; X-Frame-Options is kept for older browsers.)
const SECURITY_HEADERS = {
  "Content-Security-Policy": CSP,
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), browsing-topics=()",
};

function withSecurityHeaders(response) {
  const resp = new Response(response.body, response);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) resp.headers.set(name, value);
  return resp;
}

function withDocsHeaders(response) {
  const resp = new Response(response.body, response);
  resp.headers.set("Content-Security-Policy", DOCS_CSP);
  resp.headers.set("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload");
  resp.headers.set("X-Content-Type-Options", "nosniff");
  resp.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  return resp;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/v1" || url.pathname.startsWith("/v1/")) {
      const target = KERNEL_ORIGIN + url.pathname + url.search;
      const headers = new Headers(request.headers);
      headers.delete("host");
      // Forward the real client IP for the kernel's rate limiter, authenticated with the edge secret
      // so a direct caller to the run.app origin can't spoof it. Strip any client-supplied copies
      // first, then set the trusted values. Inert until EDGE_SECRET is configured on both sides.
      headers.delete("x-edge-auth");
      headers.delete("x-real-client-ip");
      const clientIp = request.headers.get("CF-Connecting-IP");
      if (clientIp && env.EDGE_SECRET) {
        headers.set("X-Real-Client-IP", clientIp);
        headers.set("X-Edge-Auth", env.EDGE_SECRET);
      }
      const hasBody = request.method !== "GET" && request.method !== "HEAD";
      return fetch(target, {
        method: request.method,
        headers,
        body: hasBody ? await request.arrayBuffer() : undefined,
        redirect: "manual",
      });
    }

    // Console SPA — lives at /app/ (BrowserRouter basename="/app").
    // Fallback any unmatched /app/* route to /app/index.html so React Router handles it client-side.
    if (url.pathname === "/app" || url.pathname.startsWith("/app/")) {
      const response = await env.ASSETS.fetch(request);
      if (response.status === 404) {
        const fallback = new Request(new URL("/app/index.html", request.url).toString(), request);
        return withSecurityHeaders(await env.ASSETS.fetch(fallback));
      }
      return withSecurityHeaders(response);
    }

    // Everything else → MkDocs docs (served at root, not /docs/).
    // DOCS_CSP allows Google Fonts + jsdelivr.net (Mermaid diagrams).
    return withDocsHeaders(await env.ASSETS.fetch(request));
  },
};
