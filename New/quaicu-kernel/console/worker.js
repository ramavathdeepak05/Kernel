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

    // Not an API call → serve the static console (SPA).
    return env.ASSETS.fetch(request);
  },
};
