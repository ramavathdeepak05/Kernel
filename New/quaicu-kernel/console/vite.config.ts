import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The console calls the kernel REST API. In dev, proxy /v1 → the kernel (uvicorn on :8000) so the
// browser makes same-origin requests (no CORS needed). Override the target with KERNEL_API_URL.
const KERNEL_API = process.env.KERNEL_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: KERNEL_API, changeOrigin: true },
      "/health": { target: KERNEL_API, changeOrigin: true },
    },
  },
});
