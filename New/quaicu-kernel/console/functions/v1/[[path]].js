// Cloudflare Pages Function — reverse-proxy /v1/* to the Cloud Run kernel API.
//
// This makes the console and the API share ONE origin (kernel.quaicu.org): the browser calls
// same-origin /v1/... , this Function forwards it to the Cloud Run service, and there is NO CORS
// (the browser never makes a cross-origin request; the Function→Cloud Run hop is server-side).
//
// Host header: we drop the incoming Host (kernel.quaicu.org) so the Workers runtime sets it to the
// Cloud Run origin host — Cloud Run routes by hostname and would 404 a foreign Host otherwise.
//
// If the kernel later moves behind kernel.quaicu.org directly (LB), just update KERNEL_ORIGIN.

const KERNEL_ORIGIN = "https://quaicu-kernel-152046316624.us-central1.run.app";

export async function onRequest(context) {
  const { request } = context;
  const incoming = new URL(request.url);
  const target = KERNEL_ORIGIN + incoming.pathname + incoming.search;

  const headers = new Headers(request.headers);
  headers.delete("host"); // let the runtime set Host to the Cloud Run origin

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  return fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
    redirect: "manual",
  });
}
