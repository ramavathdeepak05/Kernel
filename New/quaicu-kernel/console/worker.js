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
